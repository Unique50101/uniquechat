"""Release check: download once, then reload and generate with Hub access disabled."""
import os
import subprocess
import sys
from PIL import Image
from uniquechat.engine import Engine, TEXT, VISION

if __name__ == "__main__":
    for repo in [TEXT, VISION]:
        if "--cached" not in sys.argv:
            Engine(repo, cached=False)
            continue
        model = Engine(repo, cached=True)
        content = [{"type": "text", "text": "What is two plus two?"}]
        if model.vision:
            content = [{"type": "image", "image": Image.new("RGB", (128, 128), "red")},
                       {"type": "text", "text": "Name this color."}]
        reply = model.reply([{"role": "user", "content": content}])
        if not reply:
            raise RuntimeError(f"{repo} returned an empty response")
        print(f"{repo}: {reply}")
    if "--cached" not in sys.argv:
        subprocess.run([sys.executable, __file__, "--cached"], check=True,
                       env={**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
