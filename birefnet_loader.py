"""Load an original BiRefNet checkpoint (e.g. ToonOut's .pth) as the core background removal model.

The core "Load Background Removal Model" only accepts weights whose keys start with "bb.". Checkpoints saved
from a DataParallel / torch.compile training run (ToonOut: "module._orig_mod.bb...") are not recognised, so the
prefixes are stripped here and the rest is handed to the core loader. Files are read with weights_only=True.
"""

PREFIXES = ("module.", "_orig_mod.")


def strip_prefixes(sd):
    """Remove training-wrapper prefixes from every key (in any order, repeated)."""
    out = {}
    for k, v in sd.items():
        changed = True
        while changed:
            changed = False
            for p in PREFIXES:
                if k.startswith(p):
                    k, changed = k[len(p):], True
        out[k] = v
    return out


class LoadBiRefNetCheckpoint:
    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        return {"required": {
            "bg_removal_name": (sorted(folder_paths.get_filename_list("background_removal")),
                                {"tooltip": "A BiRefNet checkpoint in models/background_removal (.pth or .safetensors), "
                                            "e.g. ToonOut's birefnet_finetuned_toonout.pth."}),
        }}

    RETURN_TYPES = ("BACKGROUND_REMOVAL",)
    RETURN_NAMES = ("bg_model",)
    FUNCTION = "load"
    CATEGORY = "image/background removal"
    DESCRIPTION = ("Loads an original BiRefNet checkpoint such as ToonOut (anime fine-tune) for the core "
                   "Remove Background node, without converting the file.")

    def load(self, bg_removal_name):
        import comfy.bg_removal_model
        import comfy.utils
        import folder_paths
        path = folder_paths.get_full_path_or_raise("background_removal", bg_removal_name)
        sd = strip_prefixes(comfy.utils.load_torch_file(path, safe_load=True))
        model = comfy.bg_removal_model.load_background_removal_model(sd)
        if model is None:
            raise RuntimeError(f"{bg_removal_name} does not look like a BiRefNet checkpoint.")
        return (model,)
