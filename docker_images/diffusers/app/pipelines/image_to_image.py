import json
import os

import torch
from app.pipelines import Pipeline
from diffusers import (
    AltDiffusionImg2ImgPipeline,
    AltDiffusionPipeline,
    ControlNetModel,
    DiffusionPipeline,
    DPMSolverMultistepScheduler,
    StableDiffusionControlNetPipeline,
    StableDiffusionImageVariationPipeline,
    StableDiffusionImg2ImgPipeline,
    StableDiffusionInstructPix2PixPipeline,
    StableDiffusionPipeline,
    StableUnCLIPImg2ImgPipeline,
    StableUnCLIPPipeline,
)
from diffusers.models.attention_processor import AttnProcessor2_0
from huggingface_hub import hf_hub_download, model_info
from PIL import Image


class ImageToImagePipeline(Pipeline):
    def __init__(self, model_id: str):
        use_auth_token = os.getenv("HF_API_TOKEN")
        model_data = model_info(model_id, token=use_auth_token)

        kwargs = (
            {"safety_checker": None}
            if model_id.startswith("hf-internal-testing/")
            else {}
        )
        if torch.cuda.is_available():
            kwargs["torch_dtype"] = torch.float16

        # check if is controlnet or SD/AD
        config_file_name = None
        for file_name in ("config.json", "model_index.json"):
            if any(file.rfilename == file_name for file in model_data.siblings):
                config_file_name = file_name
                break
        if config_file_name:
            config_file = hf_hub_download(
                model_id, config_file_name, token=use_auth_token
            )
            with open(config_file, "r") as f:
                config_dict = json.load(f)

            model_type = config_dict.get("_class_name", None)
        else:
            raise ValueError("Model type not found")

        # load according to model type
        if model_type == "ControlNetModel":
            model_to_load = (
                model_data.cardData["base_model"]
                if "base_model" in model_data.cardData
                else "runwayml/stable-diffusion-v1-5"
            )

            controlnet = ControlNetModel.from_pretrained(
                model_id, use_auth_token=use_auth_token, **kwargs
            )
            self.ldm = StableDiffusionControlNetPipeline.from_pretrained(
                model_to_load,
                controlnet=controlnet,
                use_auth_token=use_auth_token,
                **kwargs,
            )
        elif model_type in ["AltDiffusionPipeline", "AltDiffusionImg2ImgPipeline"]:
            self.ldm = AltDiffusionImg2ImgPipeline.from_pretrained(
                model_id, use_auth_token=use_auth_token, **kwargs
            )
        elif model_type in [
            "StableDiffusionPipeline",
            "StableDiffusionImg2ImgPipeline",
        ]:
            self.ldm = StableDiffusionImg2ImgPipeline.from_pretrained(
                model_id, use_auth_token=use_auth_token, **kwargs
            )
        elif model_type in ["StableUnCLIPPipeline", "StableUnCLIPImg2ImgPipeline"]:
            self.ldm = StableUnCLIPImg2ImgPipeline.from_pretrained(
                model_id, use_auth_token=use_auth_token, **kwargs
            )
        elif model_type in [
            "StableDiffusionImageVariationPipeline",
            "StableDiffusionInstructPix2PixPipeline",
        ]:
            self.ldm = DiffusionPipeline.from_pretrained(
                model_id, use_auth_token=use_auth_token, **kwargs
            )
        else:
            raise ValueError("Model type not found or pipeline not implemented")

        if torch.cuda.is_available():
            self.ldm.to("cuda")
            self.ldm.unet.set_attn_processor(AttnProcessor2_0())

        if isinstance(
            self.ldm,
            (
                StableUnCLIPImg2ImgPipeline,
                StableUnCLIPPipeline,
                StableDiffusionPipeline,
                StableDiffusionImg2ImgPipeline,
                AltDiffusionPipeline,
                AltDiffusionImg2ImgPipeline,
                StableDiffusionControlNetPipeline,
                StableDiffusionInstructPix2PixPipeline,
                StableDiffusionImageVariationPipeline,
            ),
        ):
            self.ldm.scheduler = DPMSolverMultistepScheduler.from_config(
                self.ldm.scheduler.config
            )

    def __call__(self, image: Image.Image, prompt: str = "", **kwargs) -> "Image.Image":
        """
        Args:
            prompt (:obj:`str`):
                a string containing some text
            image (:obj:`PIL.Image.Image`):
                a condition image
        Return:
            A :obj:`PIL.Image.Image` with the raw image representation as PIL.
        """
        if "num_inference_steps" not in kwargs:
            kwargs["num_inference_steps"] = 25

        if isinstance(
            self.ldm,
            (
                StableDiffusionPipeline,
                StableDiffusionImg2ImgPipeline,
                AltDiffusionPipeline,
                AltDiffusionImg2ImgPipeline,
                StableDiffusionControlNetPipeline,
                StableDiffusionInstructPix2PixPipeline,
            ),
        ):
            images = self.ldm(prompt, image, **kwargs)["images"]
            return images[0]
        elif isinstance(self.ldm, (StableUnCLIPImg2ImgPipeline, StableUnCLIPPipeline)):
            # image comes first
            images = self.ldm(image, prompt, **kwargs)["images"]
            return images[0]
        elif isinstance(self.ldm, StableDiffusionImageVariationPipeline):
            # only image is needed
            images = self.ldm(image, **kwargs)["images"]
            return images[0]
        else:
            raise ValueError("Model type not found or pipeline not implemented")
