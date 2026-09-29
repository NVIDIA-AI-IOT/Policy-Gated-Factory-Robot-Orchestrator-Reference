# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CPU compatibility smoke test for the GR00T Qwen3-VL backbone dependency."""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from transformers import (
    Qwen2TokenizerFast,
    Qwen2VLImageProcessor,
    Qwen3VLConfig,
    Qwen3VLForConditionalGeneration,
    Qwen3VLProcessor,
    Qwen3VLVideoProcessor,
)


def run_smoke(root: Path) -> dict:
    """Exercise synthetic CPU image/text inference and a safe checkpoint round trip."""
    root.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    torch.manual_seed(42)
    tokens = {
        "[UNK]": 0,
        "hello": 1,
        "<|image_pad|>": 2,
        "<|video_pad|>": 3,
        "<|vision_start|>": 4,
        "<|vision_end|>": 5,
    }
    backend = Tokenizer(WordLevel(tokens, unk_token="[UNK]"))
    tokenizer = Qwen2TokenizerFast(
        tokenizer_object=backend,
        unk_token="[UNK]",
        additional_special_tokens=list(tokens)[2:],
    )
    image_processor = Qwen2VLImageProcessor(
        patch_size=4, temporal_patch_size=2, merge_size=2, min_pixels=64, max_pixels=64
    )
    video_processor = Qwen3VLVideoProcessor(
        patch_size=4, temporal_patch_size=2, merge_size=2, min_pixels=64, max_pixels=64
    )
    processor = Qwen3VLProcessor(
        image_processor=image_processor,
        video_processor=video_processor,
        tokenizer=tokenizer,
        chat_template='{{ messages[0]["content"] }}',
    )
    image = np.arange(8 * 8 * 3, dtype=np.uint8).reshape(8, 8, 3)
    batch = processor(
        images=image,
        text="<|vision_start|><|image_pad|><|vision_end|>",
        return_tensors="pt",
    )
    processor.save_pretrained(root / "processor")
    config = Qwen3VLConfig(
        text_config={
            "hidden_size": 32,
            "intermediate_size": 64,
            "num_hidden_layers": 2,
            "num_attention_heads": 4,
            "num_key_value_heads": 2,
            "head_dim": 8,
            "vocab_size": 32,
            "rope_scaling": {"rope_type": "default", "mrope_section": [2, 1, 1]},
        },
        vision_config={
            "hidden_size": 32,
            "intermediate_size": 64,
            "depth": 2,
            "num_heads": 4,
            "out_hidden_size": 32,
            "deepstack_visual_indexes": [0, 1],
            "patch_size": 4,
            "temporal_patch_size": 2,
            "spatial_merge_size": 2,
            "num_position_embeddings": 16,
        },
        image_token_id=2,
        video_token_id=3,
        vision_start_token_id=4,
        vision_end_token_id=5,
        attn_implementation="eager",
    )
    model = Qwen3VLForConditionalGeneration(config).eval()
    with torch.no_grad():
        logits = model(**batch).logits
        text_logits = model(input_ids=torch.tensor([[1, 1, 1, 1]])).logits
    model.save_pretrained(root / "model")
    restored = Qwen3VLForConditionalGeneration.from_pretrained(
        root / "model", attn_implementation="eager"
    ).eval()
    with torch.no_grad():
        restored_logits = restored(**batch).logits
    torch.testing.assert_close(logits, restored_logits, rtol=0, atol=0)
    values = {
        f"input_{k}": v.cpu().numpy()
        for k, v in batch.items()
        if isinstance(v, torch.Tensor)
    }
    values.update(logits=logits.numpy(), text_logits=text_logits.numpy())
    np.savez(root / "outputs.npz", **values)
    return {
        "source": __import__("transformers").__file__,
        "parameters": sum(p.numel() for p in model.parameters()),
        "output_shapes": {k: list(v.shape) for k, v in values.items()},
        "round_trip_exact": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--reference", type=Path, help="Original package outputs.npz to compare exactly"
    )
    args = parser.parse_args()
    report = run_smoke(args.output_dir)
    if args.reference is not None:
        with (
            np.load(args.reference) as original,
            np.load(args.output_dir / "outputs.npz") as candidate,
        ):
            assert set(original.files) == set(candidate.files)
            for key in original.files:
                np.testing.assert_array_equal(
                    candidate[key], original[key], err_msg=key
                )
        report["matches_reference_exactly"] = True
    print(json.dumps(report))


if __name__ == "__main__":
    main()
