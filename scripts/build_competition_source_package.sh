#!/usr/bin/env bash
set -euo pipefail

version="${1:-v1.1.0}"

if [[ ! "$version" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Version must use the form vMAJOR.MINOR.PATCH, for example v1.1.0." >&2
  exit 1
fi

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
project_dir="$(CDPATH= cd -- "$script_dir/.." && pwd)"
commit="$(git -C "$project_dir" rev-parse HEAD)"
short_commit="$(git -C "$project_dir" rev-parse --short=12 HEAD)"
source_name="CareShield-${version#v}"
submission_name="03_源码与程序_学校—姓名—手机号"
release_root="$project_dir/runtime/releases/CareShield-${version#v}-final"
package_root="$release_root/$submission_name"
source_root="$package_root/01_源代码/$source_name"
deploy_root="$package_root/02_可执行与部署"
metadata_root="$package_root/04_版本与校验"

if [[ -n "$(git -C "$project_dir" status --porcelain --untracked-files=all)" ]]; then
  echo "Working tree is not clean. Commit or remove pending changes before packaging." >&2
  exit 1
fi

if [[ -e "$release_root" ]]; then
  echo "Release directory already exists: $release_root" >&2
  exit 1
fi

for command_name in git tar zip sha256sum npm; do
  command -v "$command_name" >/dev/null || {
    echo "Required command is unavailable: $command_name" >&2
    exit 1
  }
done

mkdir -p "$source_root" "$deploy_root/frontend-dist" "$package_root/03_模型资产说明" "$metadata_root"

git -C "$project_dir" archive --format=tar HEAD | tar -xf - -C "$source_root"

submodule_commit="$(git -C "$project_dir" ls-tree HEAD third_party/GVHMR | awk '{print $3}')"
if [[ -n "$submodule_commit" ]]; then
  if ! git -C "$project_dir/third_party/GVHMR" cat-file -e "${submodule_commit}^{commit}"; then
    echo "The pinned GVHMR submodule commit is not available locally." >&2
    exit 1
  fi
  mkdir -p "$source_root/third_party/GVHMR"
  git -C "$project_dir/third_party/GVHMR" archive --format=tar "$submodule_commit" \
    | tar -xf - -C "$source_root/third_party/GVHMR"
fi

npm --prefix "$project_dir/frontend" run build
cp -a "$project_dir/frontend/dist/." "$deploy_root/frontend-dist/"
cp "$project_dir/.env.example" "$deploy_root/.env.example"
cp "$project_dir/docker-compose.yml" "$deploy_root/docker-compose.yml"
cp "$project_dir/docker-compose.cpu.yml" "$deploy_root/docker-compose.cpu.yml"
cp "$project_dir/README.md" "$deploy_root/README.md"
if [[ -f "$project_dir/docs/competition_materials/final_documents/source/04_deployment_and_technical_document.md" ]]; then
  cp "$project_dir/docs/competition_materials/final_documents/source/04_deployment_and_technical_document.md" \
    "$deploy_root/deployment_and_technical_guide.md"
fi

cat >"$deploy_root/start.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail

script_dir="\$(CDPATH= cd -- "\$(dirname -- "\$0")" && pwd)"
project_dir="\$script_dir/../01_源代码/$source_name"

if [[ ! -f "\$project_dir/.env" ]]; then
  echo "Missing \$project_dir/.env. Copy .env.example and configure local credentials first." >&2
  exit 1
fi

cd "\$project_dir"
docker compose up -d --build
docker compose ps
EOF

cat >"$deploy_root/stop.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail

script_dir="\$(CDPATH= cd -- "\$(dirname -- "\$0")" && pwd)"
project_dir="\$script_dir/../01_源代码/$source_name"

cd "\$project_dir"
docker compose down
EOF

cat >"$deploy_root/verify.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail

script_dir="\$(CDPATH= cd -- "\$(dirname -- "\$0")" && pwd)"
project_dir="\$script_dir/../01_源代码/$source_name"

cd "\$project_dir"
docker compose ps
curl -fsS http://127.0.0.1:8000/api/health
printf '\nFrontend: http://127.0.0.1:5173\n'
EOF
chmod +x "$deploy_root/start.sh" "$deploy_root/stop.sh" "$deploy_root/verify.sh"

cat >"$deploy_root/运行说明.md" <<EOF
# CareShield ${version#v} 运行说明

1. 安装 Ubuntu 22.04、Docker Engine 和 Docker Compose v2。GPU 推理还需 NVIDIA Driver 与 NVIDIA Container Toolkit。
2. 按照 \`../03_模型资产说明/模型资产清单.md\` 准备允许使用的模型权重和人体模型资产。
3. 进入 \`../01_源代码/$source_name/\`，复制 \`.env.example\` 为 \`.env\`，通过安全渠道填写本机配置。
4. 返回本目录执行 \`./start.sh\`；成功后 Compose 服务应启动，Frontend 位于 \`http://127.0.0.1:5173\`。
5. 执行 \`./verify.sh\` 检查容器状态和 Backend health。
6. 使用完毕执行 \`./stop.sh\`。脚本不使用 \`-v\`，不会主动删除数据卷。

真实凭据、模型权重、家庭音视频和运行数据库均不在本包中。完整部署边界与故障排查见项目 README 和 \`deployment_and_technical_guide.md\`。
EOF

cat >"$package_root/03_模型资产说明/模型资产清单.md" <<'EOF'
# CareShield 模型与授权资产清单

模型权重、家庭媒体和运行数据不属于源码，本 ZIP 不包含本机 `models/`、`data/` 与 `runtime/` 内容。部署者须依据源码文档准备资产。

| 模块 | 主要资产 | 默认位置或获取方式 |
|---|---|---|
| 人物检测与姿态 | Ultralytics YOLO detection / pose 权重 | `models/`，具体名称以 `.env.example` 为准 |
| 实时跌倒检测 | STGCN-Extend checkpoint | `models/fall_detection/` |
| 步态与三维人体 | MeTRAbs、GVHMR checkpoints | `models/fall-risk/` |
| 人体模型 | SMPL / SMPL-X body models | 从官方站点接受许可后下载，不得未经许可再分发 |
| 跌倒风险筛查 | KINECAL ST-GCN++ checkpoint | `models/fall-risk/kinecal/` |
| 运动功能分析 | MotionCLIP / GAITCLIP 研究资产 | `models/fall-risk/motionclip/` |
| 中文语音识别 | SenseVoiceSmall ONNX | `models/fraud/` |
| 文本复核 | Qwen Ollama model | 由 Ollama 本地拉取 |

交付模型资产时，应另附来源、版本、许可证、文件大小与 SHA-256。不得把 EZVIZ 凭据、Worker token、临时播放地址或真实家庭数据作为模型资产打包。
EOF

cat >"$package_root/README_请先阅读.md" <<EOF
# 智安护居（CareShield）${version#v} 源码与程序提交包

本包由 Git commit \`$commit\` 构建，源码目录为 \`01_源代码/$source_name/\`。

- \`01_源代码/\`：完整项目源码；GVHMR 已按仓库固定 submodule commit 展开。
- \`02_可执行与部署/\`：Docker Compose 配置、前端构建产物、环境模板和启动/停止/验收脚本。
- \`03_模型资产说明/\`：未随源码分发的权重与授权资产清单。
- \`04_版本与校验/\`：版本、commit、源码清单和逐文件 SHA-256。

本包不包含 \`.env\`、AppSecret、AccessToken、内部令牌、完整设备序列号、临时播放地址、模型权重、家庭音视频、运行记录、数据库卷、虚拟环境或 \`node_modules\`。请将文件名中的“学校—姓名—手机号”替换为报名信息。

CareShield 是容器化 Web 系统，不是单一桌面可执行文件；Docker Compose 是正式部署入口。完整 AI 功能需要合法准备模型资产和 GPU 环境。
EOF

printf '%s\n' "$version" >"$metadata_root/VERSION"
printf '%s\n' "$commit" >"$metadata_root/COMMIT"
printf '%s\n' "$submodule_commit" >"$metadata_root/GVHMR_COMMIT"
git -C "$project_dir" ls-tree -r --name-only HEAD >"$metadata_root/SOURCE_FILE_LIST.txt"

(
  cd "$package_root"
  find . -type f ! -path './04_版本与校验/FILES_SHA256SUMS.txt' -print0 \
    | sort -z \
    | xargs -0 sha256sum >"04_版本与校验/FILES_SHA256SUMS.txt"
)

(
  cd "$release_root"
  zip -q -r "$submission_name.zip" "$submission_name"
  sha256sum "$submission_name.zip" >"$submission_name.zip.sha256"
)

echo "Release created: $release_root"
echo "Git commit: $short_commit"
du -sh "$package_root" "$release_root/$submission_name.zip"
