# This script patches pyproject.toml with a static version for Docker builds.
# It's run during the Docker build stage where .git is not available.
import os, re, sys

version = os.environ.get("BUILD_VERSION") or "0.0.0"
path = sys.argv[1] if len(sys.argv) > 1 else "pyproject.toml"

with open(path) as f:
    content = f.read()

content = content.replace('dynamic = ["version"]', f'version = "{version}"')
content = re.sub(r'\n\[tool\.hatch\.version\]\n.*?(?=\n\[|$)', '', content, flags=re.DOTALL)
content = re.sub(r'\n\[tool\.hatch\]\n', '\n', content)

with open(path, 'w') as f:
    f.write(content)

print(f"Injected version {version} into {path}")
