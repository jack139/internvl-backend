import math
import base64
from io import BytesIO
import torch
import torchvision.transforms as T
from PIL import Image
from torchvision.transforms.functional import InterpolationMode
from transformers import AutoModel, AutoTokenizer

from settings import model_path


def split_model(model_name, gpu_num, main_gpu=0):
    device_map = {}
    world_size = gpu_num #torch.cuda.device_count()
    num_layers = {
        'InternVL2_5-1B': 24, 'InternVL2_5-2B': 24, 'InternVL2_5-4B': 36, 'InternVL2_5-8B': 32,
        'InternVL2_5-26B': 48, 'InternVL2_5-38B': 64, 'InternVL2_5-78B': 80}[model_name]
    # Since the first GPU will be used for ViT, treat it as half a GPU.
    num_layers_per_gpu = math.ceil(num_layers / (world_size - 0.5))
    num_layers_per_gpu = [num_layers_per_gpu] * world_size
    num_layers_per_gpu[0] = math.ceil(num_layers_per_gpu[0] * 0.5)
    layer_cnt = 0
    for i, num_layer in enumerate(num_layers_per_gpu):
        for j in range(num_layer):
            device_map[f'language_model.model.layers.{layer_cnt}'] = i
            layer_cnt += 1
    device_map['vision_model'] = main_gpu
    device_map['mlp1'] = main_gpu
    device_map['language_model.model.tok_embeddings'] = main_gpu
    device_map['language_model.model.embed_tokens'] = main_gpu
    device_map['language_model.output'] = main_gpu
    device_map['language_model.model.norm'] = main_gpu
    device_map['language_model.model.rotary_emb'] = main_gpu
    device_map['language_model.lm_head'] = main_gpu
    device_map[f'language_model.model.layers.{num_layers - 1}'] = main_gpu

    return device_map


IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

def build_transform(input_size):
    MEAN, STD = IMAGENET_MEAN, IMAGENET_STD
    transform = T.Compose([
        T.Lambda(lambda img: img.convert('RGB') if img.mode != 'RGB' else img),
        T.Resize((input_size, input_size), interpolation=InterpolationMode.BICUBIC),
        T.ToTensor(),
        T.Normalize(mean=MEAN, std=STD)
    ])
    return transform


def find_closest_aspect_ratio(aspect_ratio, target_ratios, width, height, image_size):
    best_ratio_diff = float('inf')
    best_ratio = (1, 1)
    area = width * height
    for ratio in target_ratios:
        target_aspect_ratio = ratio[0] / ratio[1]
        ratio_diff = abs(aspect_ratio - target_aspect_ratio)
        if ratio_diff < best_ratio_diff:
            best_ratio_diff = ratio_diff
            best_ratio = ratio
        elif ratio_diff == best_ratio_diff:
            if area > 0.5 * image_size * image_size * ratio[0] * ratio[1]:
                best_ratio = ratio
    return best_ratio


def dynamic_preprocess(image, min_num=1, max_num=12, image_size=448, use_thumbnail=False):
    orig_width, orig_height = image.size
    aspect_ratio = orig_width / orig_height

    # calculate the existing image aspect ratio
    target_ratios = set(
        (i, j) for n in range(min_num, max_num + 1) for i in range(1, n + 1) for j in range(1, n + 1) if
        i * j <= max_num and i * j >= min_num)
    target_ratios = sorted(target_ratios, key=lambda x: x[0] * x[1])

    # find the closest aspect ratio to the target
    target_aspect_ratio = find_closest_aspect_ratio(
        aspect_ratio, target_ratios, orig_width, orig_height, image_size)

    # calculate the target width and height
    target_width = image_size * target_aspect_ratio[0]
    target_height = image_size * target_aspect_ratio[1]
    blocks = target_aspect_ratio[0] * target_aspect_ratio[1]

    # resize the image
    resized_img = image.resize((target_width, target_height))
    processed_images = []
    for i in range(blocks):
        box = (
            (i % (target_width // image_size)) * image_size,
            (i // (target_width // image_size)) * image_size,
            ((i % (target_width // image_size)) + 1) * image_size,
            ((i // (target_width // image_size)) + 1) * image_size
        )
        # split the image
        split_img = resized_img.crop(box)
        processed_images.append(split_img)
    assert len(processed_images) == blocks
    if use_thumbnail and len(processed_images) != 1:
        thumbnail_img = image.resize((image_size, image_size))
        processed_images.append(thumbnail_img)
    return processed_images


def load_image(image, input_size=448, max_num=12):
    #image = Image.open(image_file).convert('RGB')
    transform = build_transform(input_size=input_size)
    images = dynamic_preprocess(image, image_size=input_size, use_thumbnail=True, max_num=max_num)
    pixel_values = [transform(image) for image in images]
    pixel_values = torch.stack(pixel_values)
    return pixel_values


# 将 base64 编码的图片转为 PIL.Image
def load_image_b64(b64_data):
    data = base64.b64decode(b64_data) # Bytes
    tmp_buff = BytesIO(data)
    img = Image.open(tmp_buff).convert('RGB')
    tmp_buff.close()
    return img


class VLChat():
    def __init__(self, path, gpu_num=1, main_gpu=0):
        if gpu_num > 1:
            print('Multi GPUs ...', gpu_num, main_gpu)
            # load a model using multiple GPUs
            device_map = split_model('InternVL2_5-1B', gpu_num, main_gpu)
            self.model = AutoModel.from_pretrained(
                path,
                torch_dtype=torch.bfloat16,
                device_map=device_map,
                #load_in_8bit=True,
                low_cpu_mem_usage=True,
                use_flash_attn=True,
                trust_remote_code=True).eval() #.cuda()
        else:
            print('Single GPU ...')
            self.model = AutoModel.from_pretrained(
                path,
                torch_dtype=torch.bfloat16,
                #load_in_8bit=True,
                #load_in_4bit=True,
                low_cpu_mem_usage=True,
                use_flash_attn=True,
                trust_remote_code=True).eval().cuda()
        self.tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True, use_fast=False)
        self.generation_config = dict(max_new_tokens=1024, do_sample=True)

    def chat_w_image(self, question, image, max_num=12):
        # set the max number of tiles in `max_num`
        pixel_values = load_image(image, max_num=max_num).to(torch.bfloat16).cuda()
        # single-image single-round conversation (单图单轮对话)
        _question = f"<image>\n{question}"
        response = self.model.chat(self.tokenizer, pixel_values, _question, self.generation_config)
        #print(f'User: {_question}\nAssistant: {response}')
        return response


if __name__ == '__main__':
    import sys
    import readline

    if len(sys.argv)<2:
        print("usage: ochat.py <image-path>")
        sys.exit(2)

    image_path = sys.argv[1]

    image = Image.open(image_path).convert('RGB')

    vlchat = VLChat(model_path)

    while True:
        question = input("请输入您的问题：")
        if len(question.strip())==0:
            sys.exit(0)

        print("\n回答：\n", vlchat.chat_w_image(question, image))

    # OCR获取图片中的文字，只返回OCR的结果