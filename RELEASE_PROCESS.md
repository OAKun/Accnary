# Accnary 发布规则

本文规定 Accnary 源码与 Windows 程序的发布方式。发布渠道分工如下：

- **GitHub**：维护源码、测试、文档、许可证和版本标签。仓库：<https://github.com/OAKun/Accnary>。
- **CNB / ToolHub**：分发 Windows 单文件 `Accnary.exe`，并提供客户端更新清单。ToolHub：<https://cnb.cool/oakun/ToolHub>。

GitHub 源码仓库不附加 EXE。CNB 的 `accnary-vX.Y.Z` 不可变版本 Release 只上传 `Accnary.exe`；共享的 `latest` Release 还会由 ToolHub 维护更新所需的清单、SHA-256 和兼容元数据，这些不是额外的 Accnary 程序包。

## 1. 版本规则

- 唯一版本源是 `frame/app/version.py` 中的 `APP_VERSION`。ToolHub 的 `tools.json` 从该文件读取版本，不要在其他文件另设版本号副本。
- 使用 `MAJOR.MINOR.PATCH` 三段式版本号。当前已发布版本是 `0.1.0`：兼容性修复递增 PATCH；新增功能递增 MINOR；达到稳定的 `1.0.0` 后，不兼容变更递增 MAJOR。`0.x` 阶段的不兼容变更也递增 MINOR，并在说明中写明。
- **CNB 已发布的版本号不可复用。** 同一版本的二进制、源码或发布内容不能替换；要发布新内容，必须先递增版本号。
- 每次发布同步更新发布输入 `release/RELEASE_NOTES.md`，标题版本号与 `APP_VERSION` 一致，写清用户可见的变化和已知限制。当前根目录 `.gitignore` 排除了整个 `release/`，因此该文件是本机 ToolHub 发布输入，不属于 GitHub 源码仓库；在新工作副本发布时须先准备该文件。ToolHub 的 Accnary 条目从该文件读取更新说明。
- 发布标签使用 `vX.Y.Z`，例如 `v0.1.1`；标签必须指向与待发布 EXE 对应的源码提交。

## 2. 发布前检查与构建

1. 确认当前 Accnary 源码树没有不相关改动；检查待提交文件，确保没有密码库、备份、密钥、令牌、`.venv`、构建产物或真实凭据。测试只使用隔离的虚构 KDBX。
2. 更新 `frame/app/version.py` 和 `release/RELEASE_NOTES.md`，运行完整回归测试：

   ```powershell
   Set-Location 'D:\Code\Python\Tools\Software\Accnary\frame'
   .\.venv\Scripts\python.exe -B -m pytest tests -p no:cacheprovider
   ```

3. 使用项目固定构建流程，不运行临时 PyInstaller 命令：

   ```powershell
   .\.venv\Scripts\python.exe build_exe.py
   ```

   构建脚本会使用 `Accnary.spec`，验证打包 EXE 并更新 `release/Accnary.exe` 与 `release/Accnary.exe.sha256`，然后清理 `frame/build`、`frame/dist` 和本次生成的缓存。若 Accnary 正在运行，脚本会安全停止构建；必须由用户正常关闭后重试，不得强制结束进程。

4. 确认构建自检与 GUI 启动检查通过；核对 EXE 版本、大小和 SHA-256 与旁边的 `.sha256` 文件相符。确认真实密码库及其 `.bak`、`.lock` 文件未被改动或加入待提交列表。
5. 只暂存本次预期的源码与文档文件，检查 `git status`、`git diff --cached --check` 和暂存差异后提交到 GitHub `main`。确认构建所用源码与提交一致，再创建注释标签并推送：

   ```powershell
   # 先只 git add 本次明确变更的源码与文档文件，不要暂存本机数据或构建产物。
   git diff --cached --check
   git diff --cached --stat
   git commit -m 'release: Accnary X.Y.Z'
   git tag -a vX.Y.Z -m 'Accnary X.Y.Z'
   git push origin main --follow-tags
   ```

   只有确认本地源码提交就是刚才构建所用的源码后，才创建和推送标签。不要移动或覆盖已发布的标签。

## 3. 发布到 CNB / ToolHub

只使用 ToolHub 的统一发布器，并明确限定 Accnary。未设置范围时，发布器可能处理 ToolHub 登记的其他产品。

```powershell
Set-Location 'D:\Code\Python\Tools\Software\ToolHub'
$env:TOOLHUB_ONLY_APP_IDS = 'accnary'
& 'D:\Programs\Python\python.exe' .\publish.py
Remove-Item Env:TOOLHUB_ONLY_APP_IDS
```

- 发布器读取 `ToolHub/tools.json` 中 Accnary 的版本源和 `release/Accnary.exe`，计算校验值，创建 `accnary-vX.Y.Z` 不可变 Release，并更新共享 `latest` 与线上 `manifest.json`。
- 范围发布以线上 manifest 为基线，只合并 Accnary 条目；不得改写或删除 Finance 及其他产品的 manifest 条目、附件或配置。不要在本流程中运行无范围限制的全产品发布。
- CNB 令牌只保存在 ToolHub 本机忽略文件或 `CNB_TOKEN` 环境变量中；不得写入 Accnary 源码、GitHub、日志、EXE 或发布清单。
- 发布器生成的本地暂存文件位于 `ToolHub/dist/`。线上验证完成后，只清理本次的 `Accnary.exe`、`Accnary.sha256` 和 `Accnary.update.json`；保留 `manifest.json` 及其他产品的暂存文件。

## 4. 发布后验收

发布成功后逐项核对：

1. GitHub `main` 与 `vX.Y.Z` 标签指向正确的源码提交；源码仓库没有 EXE、KDBX、备份、密钥或令牌。
2. CNB 清单中的 Accnary 版本、EXE 大小、SHA-256 与本地已验收产物一致。
3. `accnary-vX.Y.Z` 下载地址可匿名下载，实际下载内容的 SHA-256 与清单一致；`latest/Accnary.exe` 也可用。
4. 对比发布前后的 manifest，确认所有非 Accnary 产品条目保持不变，特别确认 Finance 未变化。
5. 留存版本号、Git 提交/标签、EXE 大小和 SHA-256、测试结果及远端验收结果。出现上传或校验失败时先停止并排查；不得用相同版本上传不同内容。

下载地址格式：

```text
不可变版本：https://cnb.cool/oakun/ToolHub/-/releases/download/accnary-vX.Y.Z/Accnary.exe
最新版：    https://cnb.cool/oakun/ToolHub/-/releases/download/latest/Accnary.exe
版本清单：  https://cnb.cool/oakun/ToolHub/-/git/raw/main/manifest.json
```

Accnary 更新客户端以 ToolHub `manifest.json` 中 `apps.accnary` 的 SemVer 和 SHA-256 为准；下载或安装仍需用户确认。不得把自动更新改成静默下载或静默替换。
