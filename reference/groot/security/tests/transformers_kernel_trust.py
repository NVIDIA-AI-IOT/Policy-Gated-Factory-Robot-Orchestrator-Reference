# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Independent regression for kernel namespace validation versus 4.57.6 parser.
No Hub requests or remote code execution: get_kernel is always mocked.
"""

import unittest
from unittest import mock

from transformers.integrations import hub_kernels


class KernelTrustRegression(unittest.TestCase):
    def test_untrusted_or_ambiguous_kernel_strings_never_reach_loader(self):
        for value in (
            "attacker/kernels",
            "paged|attacker/kernels",
            "kernels-community/ignored|attacker:fn",
            "kernels-community/ignored@v1|attacker:fn",
            "paged|kernels-community/ignored|attacker:fn",
            "kernels-community/flash-attn\n",
        ):
            with self.subTest(value=value):
                self.assertFalse(hub_kernels.is_kernel(value))
                with (
                    mock.patch.object(hub_kernels, "_kernels_available", True),
                    mock.patch.object(
                        hub_kernels,
                        "get_kernel",
                        create=True,
                        side_effect=RuntimeError("mock only"),
                    ) as loader,
                ):
                    hub_kernels.load_and_register_kernel(value)
                    loader.assert_not_called()

    def test_trusted_names_parse_to_trusted_repo(self):
        for value in (
            "kernels-community/flash-attn",
            "kernels-community/flash-attn@v1:fn",
            "paged|kernels-community/flash-attn@v1:fn",
            "sdpa|kernels-community/flash-attn@v1:fn",
        ):
            with self.subTest(value=value):
                self.assertTrue(hub_kernels.is_kernel(value))
                with (
                    mock.patch.object(hub_kernels, "_kernels_available", True),
                    mock.patch.object(
                        hub_kernels,
                        "get_kernel",
                        create=True,
                        side_effect=RuntimeError("mock only"),
                    ) as loader,
                ):
                    with self.assertRaisesRegex(ValueError, "mock only"):
                        hub_kernels.load_and_register_kernel(value)
                    loader.assert_called_once_with(
                        "kernels-community/flash-attn",
                        revision="v1" if "@" in value else None,
                    )

    def test_standard_attention_does_not_use_hub_kernel_loader(self):
        for value in (
            None,
            "eager",
            "sdpa",
            "flash_attention_2",
            "flash_attention_3",
            "flex_attention",
        ):
            with self.subTest(value=value):
                self.assertFalse(hub_kernels.is_kernel(value))


if __name__ == "__main__":
    unittest.main(verbosity=2)
