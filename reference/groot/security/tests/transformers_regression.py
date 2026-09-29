# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import random
import types
from unittest.mock import patch

import numpy as np
import pytest
import torch
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from transformers import (
    LightGlueConfig,
    PretrainedConfig,
    PreTrainedTokenizerFast,
    ProcessorMixin,
    Trainer,
)
from transformers.integrations.hub_kernels import is_kernel
from transformers.models.qwen3_vl.configuration_qwen3_vl import Qwen3VLConfig
from transformers.training_args import ParallelMode


class EmptyProcessor(ProcessorMixin):
    attributes = []


def tokenizer():
    backend = Tokenizer(WordLevel({"[UNK]": 0, "hello": 1}, unk_token="[UNK]"))
    return PreTrainedTokenizerFast(tokenizer_object=backend, unk_token="[UNK]")


@pytest.mark.parametrize(
    "field", ["_attn_implementation_internal", "_experts_implementation_internal"]
)
def test_internal_attention_fields_not_loaded(field):
    config = PretrainedConfig.from_dict({field: "untrusted-account/kernel"})
    assert getattr(config, field, None) is None


@pytest.mark.parametrize(
    "name",
    [
        "attacker/kernels",
        "attacker/kernels@v1",
        "attacker/kernels:fn",
        "paged|attacker/kernels",
        "kernels-community/ignored|attacker:fn",
        "kernels-community/ignored|attacker/evil",
        "kernels-community/x|attacker/evil|second",
        "kernels-community/x\n",
    ],
)
def test_unknown_kernel_rejected(name):
    assert not is_kernel(name)


@pytest.mark.parametrize(
    "name",
    [
        "kernels-community/flash-attn",
        "kernels-community/flash-attn@v1:attn",
        "paged|kernels-community/flash-attn",
        "sdpa|kernels-community/flash-attn",
    ],
)
def test_trusted_kernel_supported(name):
    assert is_kernel(name)


def test_normal_config_and_lightglue_supported():
    assert PretrainedConfig(attn_implementation="sdpa")._attn_implementation == "sdpa"
    config = LightGlueConfig(keypoint_detector_config={"model_type": "superpoint"})
    assert config.keypoint_detector_config.model_type == "superpoint"


def test_lightglue_does_not_load_nested_remote_config():
    with patch(
        "transformers.AutoConfig.from_pretrained",
        side_effect=RuntimeError("untrusted remote loading"),
    ) as remote:
        with pytest.raises(KeyError):
            LightGlueConfig(
                trust_remote_code=True,
                keypoint_detector_config={
                    "model_type": "unregistered",
                    "_name_or_path": "attacker/repo",
                },
            )
    remote.assert_not_called()


@pytest.mark.parametrize("kind", ["tokenizer", "processor"])
@pytest.mark.parametrize(
    "name", ["../../ESCAPED", "/tmp/PGFR_NOSUCH_ABSOLUTE_ESCAPE", "nested/name"]
)
def test_chat_template_traversal_rejected(tmp_path, kind, name):
    obj = tokenizer() if kind == "tokenizer" else EmptyProcessor()
    obj.chat_template = {"default": "hello", name: "untrusted"}
    # Absolute escape stays inside the disposable test directory if the original is vulnerable.
    if name.startswith("/"):
        name = str(tmp_path / "ABSOLUTE_ESCAPE")
        obj.chat_template = {"default": "hello", name: "untrusted"}
    with pytest.raises(ValueError, match="Invalid chat template name"):
        obj.save_pretrained(tmp_path / "output")
    assert not (tmp_path / "ESCAPED.jinja").exists()
    assert not (tmp_path / "ABSOLUTE_ESCAPE.jinja").exists()


@pytest.mark.parametrize("kind", ["tokenizer", "processor"])
def test_valid_chat_templates_preserved(tmp_path, kind):
    obj = tokenizer() if kind == "tokenizer" else EmptyProcessor()
    obj.chat_template = {"default": "hello", "tool_use": "tool"}
    obj.save_pretrained(tmp_path / "output")
    assert (tmp_path / "output/chat_template.jinja").read_text() == "hello"
    assert (
        tmp_path / "output/additional_chat_templates/tool_use.jinja"
    ).read_text() == "tool"


def test_trainer_rng_explicit_safe_load_and_restoration(tmp_path):
    state = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "cpu": torch.random.get_rng_state(),
    }
    torch.save(state, tmp_path / "rng_state.pth")
    expected = (random.random(), np.random.random(), torch.rand(1))
    args = types.SimpleNamespace(world_size=1, parallel_mode=ParallelMode.NOT_PARALLEL)
    with patch("torch.load", wraps=torch.load) as loader:
        Trainer._load_rng_state(types.SimpleNamespace(args=args), str(tmp_path))
    assert loader.call_args.kwargs.get("weights_only") is True
    actual = (random.random(), np.random.random(), torch.rand(1))
    assert actual[0] == expected[0]
    assert actual[1] == expected[1]
    torch.testing.assert_close(actual[2], expected[2], rtol=0, atol=0)


def test_qwen3vl_config_round_trip(tmp_path):
    c = Qwen3VLConfig(
        text_config={
            "hidden_size": 32,
            "intermediate_size": 64,
            "num_hidden_layers": 2,
            "num_attention_heads": 4,
            "num_key_value_heads": 2,
            "head_dim": 8,
            "vocab_size": 32,
        },
        vision_config={
            "hidden_size": 32,
            "intermediate_size": 64,
            "depth": 2,
            "num_heads": 4,
            "out_hidden_size": 32,
            "deepstack_visual_indexes": [0, 1],
        },
    )
    c.save_pretrained(tmp_path)
    restored = Qwen3VLConfig.from_pretrained(tmp_path)
    assert restored.to_dict() == c.to_dict()


@pytest.mark.parametrize("trust", ["True", "False"])
def test_transfoxl_pickle_vocab_disabled_even_when_opted_in(
    tmp_path, monkeypatch, trust
):
    import pickle

    from transformers.models.deprecated.transfo_xl import tokenization_transfo_xl as xl

    monkeypatch.setenv("TRUST_REMOTE_CODE", trust)
    vocab = tmp_path / "vocab.pkl"
    vocab.write_bytes(pickle.dumps({"idx2sym": ["<unk>"], "sym2idx": {"<unk>": 0}}))
    with patch.object(
        xl.pickle, "load", side_effect=AssertionError("raw pickle loader reached")
    ) as loader:
        with pytest.raises(ValueError):
            xl.TransfoXLTokenizer(pretrained_vocab_file=str(vocab))
    loader.assert_not_called()


def test_transfoxl_plain_text_vocab_preserved(tmp_path):
    from transformers.models.deprecated.transfo_xl.tokenization_transfo_xl import (
        TransfoXLTokenizer,
    )

    vocab = tmp_path / "vocab.txt"
    vocab.write_text("<unk>\n<eos>\nhello\nworld\n")
    tokenizer = TransfoXLTokenizer(vocab_file=str(vocab))
    assert tokenizer.convert_tokens_to_ids(["hello", "world"]) == [2, 3]
    assert tokenizer.tokenize("hello world") == ["hello", "world"]


def test_transfoxl_pickle_corpus_disabled(tmp_path, monkeypatch):
    import pickle

    from transformers.models.deprecated.transfo_xl import tokenization_transfo_xl as xl

    monkeypatch.setenv("TRUST_REMOTE_CODE", "True")
    (tmp_path / "cache.pkl").write_bytes(pickle.dumps({"payload": "unused"}))
    with patch.object(
        xl.pickle, "load", side_effect=AssertionError("raw pickle loader reached")
    ) as loader:
        with pytest.raises(ValueError, match="pickle corpus caches are disabled"):
            xl.get_lm_corpus(str(tmp_path), "ptb")
    loader.assert_not_called()


def test_transfoxl_safe_torch_cache_preserved(tmp_path):
    from transformers.models.deprecated.transfo_xl.tokenization_transfo_xl import (
        get_lm_corpus,
    )

    expected = torch.arange(4)
    torch.save({"tokens": expected}, tmp_path / "cache.pt")
    with patch("torch.load", wraps=torch.load) as loader:
        actual = get_lm_corpus(str(tmp_path), "ptb")
    assert loader.call_args.kwargs.get("weights_only") is True
    torch.testing.assert_close(actual["tokens"], expected)
