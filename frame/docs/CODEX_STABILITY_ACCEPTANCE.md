# Accnary 0.4.0 稳定性验收记录

日期：2026-10-26  
范围：相对默认库路径、全量回归、保存/恢复故障覆盖、串行后台存储任务、性能测量、隔离 EXE 验收与最新构建。

## 结论

最新源码全量自动化回归 **241/241 通过**（33 个模块由 Pex 自动调度，0 失败、0 错误、0 跳过）。分类切换的第二轮回归补入 535 Qt 逻辑像素窄窗口：发现并修复了选择分类后侧栏自动收起、列表随之位移的问题。固定构建、真实窗口启动 smoke、EXE `--check` 与 promote 均通过。当前 `release/Accnary.exe` 为 **46,109,272 字节**，SHA-256 `337df629e5e7841c9275c5a0552acc5f31827081f373cbbda859d86e61c7fa00`，sidecar 匹配。最新回归明细见 `docs/category-switch-repair-20261026/pytest-results-full-20261026.txt`。

这不等于生产安全验收。仍有一个已复现的 P0 数据覆盖窗口：KeePassXC 等外部程序不遵守 Accnary 的跨进程锁协议，如果在 Accnary 最后一次外部修改检查之后写入同一密码库，该次外部写入可能被 Accnary 替换文件时覆盖。使用同一个 KDBX 文件时，不应让 Accnary 和其他可写客户端同时编辑。

所有本轮测试凭据均为虚构数据；未打开、读取或修改 `Accnary\\data` 中的任何文件。测试设置和 KDBX 均位于隔离临时目录。

## 相对默认密码库路径

- 解锁页显示并保留相对路径 `./data/Accnary.kdbx`。
- 打包运行时以 `sys.executable` 所在目录为基准解析；源码运行时以 `frame` 源码根目录为基准。代码不依赖 `release` 目录名，也不依赖当前工作目录。
- 当前 EXE 放在 `release` 文件夹，因此此布局下相对路径最终指向 EXE 旁的 `data/Accnary.kdbx`；源码中保存和显示的仍是相对路径。
- 用户显式选择的绝对路径保持不变；最近使用路径在写入设置前标准化为绝对路径。
- 4 项路径测试覆盖当前目录变化、源码路径、任意 EXE 所在目录、临时构建布局及绝对路径。
- 最新隔离版 EXE 从项目目录以外的工作目录启动，使用默认路径创建虚构 KDBX。文件落在 EXE 所在目录旁的 `data` 子目录，工作目录下没有创建同名库。

实现位于 `app/ui/unlock_dialog.py`，回归用例位于 `tests/audit/test_default_vault_path.py`。

## 自动化回归

以下回归针对搜索与索引优化后的最新源码。使用项目 `.venv`，通过本机 Pex 自动调度 32 个测试模块；每个模块使用独立 QSettings 目录和 pytest 临时目录，测试只使用虚构凭据。

- 223 passed
- 0 failed
- 0 errors
- 0 skipped

重点覆盖保存中断、替换后进程终止、恢复过程终止、备份重新解锁、多个 Accnary 写入冲突、外部修改检测、复杂账户数据、KeePassXC 兼容性、锁定后的内存索引清理和明文落盘检查。

保存/恢复故障测试会重新打开目标库与加密快照并核对内容，不只检查返回值。逐模块退出码、数量和 pytest 输出保存在本报告引用的结果文件中；该源码版本记录为 32 模块、223 项全通过。

逐模块输出保存在 `stability-acceptance-20261026/pytest-results-full-20261026.txt`。首轮尝试报告（220 passed、3 failed）及修复后报告均保留。另有以下检查通过：

- 源码版 `main.py --check`：Python 3.14.9、PyKeePass 4.2.0、PySide6/Qt 6.12.0，`stack OK`。
- 源码版 `main.py --smoke`：`smoke OK`。
- 新 EXE `--check`：退出码 0。
- 固定构建脚本内的真实窗口启动 smoke：通过。

## 隔离 EXE 桌面检查

使用 `frame/dist/Accnary.exe`、UI Automation 控件接口及独立的虚构密码库完成：

1. 从项目目录外启动解锁页，确认界面显示相对默认路径。
2. 使用默认相对路径创建虚构 KDBX，独立重开并校验文件位置及内容。
3. 打开含 QQ、NASA Earthdata、付费软件三条虚构记录的 KDBX。
4. 搜索 `QQ`，结果定位到 QQ 主账号。
5. 搜索长网址片段 `urs.earthdata.nasa.gov`，结果定位到 NASA Earthdata 记录。
6. 搜索付费软件账户，确认登录方式、微信授权、邮箱和许可证分组显示。
7. 关闭主窗口后，EXE 进程以退出码 0 退出；再次独立解锁虚构 KDBX，三条记录及微信登录、许可证数据均完整。

保存的截图均来自打包 EXE，数据为虚构且密码保持遮蔽：

- `stability-acceptance-20261025/unlock-default-relative.png`
- `stability-acceptance-20261025/exe-main-qq.png`
- `stability-acceptance-20261025/exe-search-url-fragment.png`
- `stability-acceptance-20261025/exe-main-complex.png`

UI Automation 的 `Invoke` 没有成功让锁定按钮弹出可观察的嵌套解锁对话框，因此**本轮不将打包 EXE 的锁定/重新解锁列为桌面黑盒通过项**。这只是自动化触发限制的观察结果，不能据此判断为产品缺陷。

另在隔离 Qt 事件循环中运行了真实 `MainWindow.lock_and_unlock()` 和真实 `UnlockDialog`，由定时器向主密码控件填入虚构主密码；锁定、重新解锁、关闭、重新打开 KDBX 并核对记录均通过。此项证明源码的 Qt 控件/业务接线路径可用，但不替代打包 EXE 上的独立 UIA 点击验收。若需要打包 EXE 层面的单独确认，需要可稳定触发 Qt `QToolButton` 的自动化接口或人工验收。

## 性能观察与后台存储

后台化之前的虚构库基准：

- 100 条：保存 0.691 秒，Qt 计时器最大间隔 0.706 秒。
- 500 条：保存 0.893 秒，Qt 计时器最大间隔 0.893 秒。
- 2000 条：创建并添加约 26.5 秒，解锁 0.996 秒，保存 1.871 秒，Qt 计时器最大间隔 1.879 秒。
- 500 条保存的 cProfile 中，两次 Argon2 派生约 0.602 秒，临时 KDBX 重开验证约 0.326 秒。没有删减这些安全校验。

新增 `app/ui/storage_task.py`，将解锁/创建、保存、主密码修改、备份导出/验证/恢复及保存后重读放入单一串行工作线程。应用模态进度窗口不可取消；执行期间暂停空闲锁定计时，锁定/退出请求延后处理，避免工作线程与会话清理并发。错误在 UI 线程按原类型处理，并清除工作线程异常回溯，避免回溯长期持有密码输入闭包。KDBX 写入、快照、格式校验和加密参数均未改变。

后台保存实测：

- 100 条虚构账户：保存 0.729 秒、计时器 48 次、最大事件间隔 0.016 秒；重新打开验证 100 条。
- 2000 条虚构账户：保存 1.675 秒、计时器 111 次、最大事件间隔 0.023 秒；重新打开验证 2000 条。
- 新增 3 项测试验证事件循环持续响应、存储异常向调用方传播及主窗口串行调度钩子；全套测试共 223 项通过。

以上耗时来自当前机器的虚构数据库，不代表其他设备或真实密码库的绝对性能。账户批量录入仍由 PyKeePass 的逐项重复项检查主导；本轮没有改变重复账户语义。

## 重要安全发现与限制

### P0：外部写入的最后检查竞态仍存在

使用隔离 KDBX 可重复构造：Accnary 完成最后一次内容摘要检查后，独立外部写入者修改数据库，随后 Accnary 执行原子替换；外部较新的内容会被覆盖。现有锁只能协调遵守 Accnary 协议的其他 Accnary 实例，不能强制 KeePassXC 等客户端参与。

因此目前只能明确限制为：编辑期间不要用 KeePassXC 或其他工具同时写同一个密码库。构建和本轮测试没有声称消除此竞态，也没有引入未经验证的跨软件锁协议。

另以临时文件验证了 Windows 共享模式：拒绝 `FILE_SHARE_WRITE` 能阻挡直接写句柄，但为了让 Accnary 原子替换必须允许删除共享；外部程序仍可用 `ReplaceFileW` 原子替换目标。保持不允许删除的句柄则会使当前保存替换失败。因此本轮没有加入不完整的 Win32 常驻锁，P0 限制不变。

### 其他边界

- 大部分 KDBX 加密和磁盘操作已移出 UI 线程；应用模态进度页期间禁用交互。账户列表重建、模型快照等普通 UI 工作仍可能随数据量增长。
- Python 托管的密码字符串可能存在多个副本，无法保证像受控原生内存缓冲区那样彻底擦除。
- 自动化故障注入和子进程终止不是断电测试；未模拟真实断电或硬件故障。
- Accnary 仍未经独立第三方安全审计，也没有代码签名。
- 因 P0 外部写入竞态未消除，当前结果不能作为“生产安全已验收”的依据。

## 最新构建

从最新源码通过固定 `build_exe.py --validate-only` 和已提交的 `Accnary.spec` 构建到 `frame/dist`。隔离验收通过后使用 `build_exe.py --promote` 更新正式输出；构建器先检查运行中的本项目实例，不会强制结束进程。原有 release 文件在隔离验证完成前保持不变。

- 版本：0.4.0 测试版
- 文件：`release/Accnary.exe`
- 大小：46,103,662 字节（约 43.97 MiB）
- SHA-256：`a0755af21d54a76ed44e0e958ec6814b0823698ec8a10635983cf6d46ae9e668`
- `release/Accnary.exe.sha256` 已更新并与 EXE 一致
- `release/Accnary.exe --check` 退出码：0
- 提升后已确认 `frame/dist`、`frame/build`、`.pytest_cache`、源码 `__pycache__`、独立 Pex 临时 runner 和构建生成的 `assets/app-icon.ico` 均已清理；本轮没有触碰 `release/data` 或项目 `data` 中的密码库

## 2026-10-26 搜索与列表刷新优化

- 搜索保持输入即响应，但搜索变化时不再重建不变的分类导航；匹配超过 50 条时显示“50+ 个结果”，避免把截断列表误报为总数。列表清空与重建期间暂停绘制，并用 `finally` 恢复更新状态。
- 分类数量导航只在启动、数据变化、恢复、冲突重载和重新解锁等显式刷新时更新；搜索字符变化时跳过该步。
- 身份索引构建改用 UUID 字典查找，避免每个登录/绑定引用都线性扫描全局身份表；保持重复 UUID 时先匹配首条的既有行为。
- 固定构建脚本 `--validate-only`、真实窗口 smoke、`--check` 和 `--promote` 均通过，SHA sidecar 一致。构建产物、缓存和构建生成的 `app-icon.ico` 已清理；下次构建脚本会从 PNG 自动重建 ICO。
- 全量 pytest：32 模块、223 passed、0 failed/errors/skipped。长列表实际刷新耗时尚未单独测量。

## 2026-10-26 五十项优化跟进

- 完成 50 项针对性检查，明细见 `CODEX_50_ITERATIONS.md`。不是 50 次大规模重写；只对有复现依据的问题做局部修复。
- 新增 UI 回归后全量测试为 **33 个模块、237 passed、0 failed、0 errors、0 skipped**，使用 Pex 一次提交全部自然独立模块，自动选择 20 个 worker；各模块设置目录隔离。
- 首轮完整回归暴露长网址搜索排序退化：查询 `example.invalid/portal` 时只共享基础域名的无关子域排在目标网址前。按 URL path 匹配增加相关性，单模块 8/8 及后续全量 237/237 通过。首轮记录保存在 `CODEX_50_ITERATIONS/pytest-results-url-regression-before-fix-20261026.txt`。
- 复杂账户 Qt 控件截图发现长详情卡片被压缩，部分字段重叠。给滚动内容外层布局设最小尺寸约束后，虚构详情页滚动范围约 593 px，各卡片至少达到最小高度；回归用例检查滚动范围及卡片高度。截图位于 `CODEX_50_ITERATIONS/screenshots/`。
- 其他局部修正包括：窗口显示后恢复 splitter 状态、许可证密钥保留前后空格并默认遮蔽、生成密码默认遮蔽、空受保护字段显示“未填写”、搜索 tooltip 转义/可访问描述、等分搜索命中优先最近使用、结果上限提示和创建密码库时说明主密码无法找回。
- 固定 `build_exe.py --validate-only` 的构建、Windows 桌面解锁页 smoke、EXE `--check` 均通过；`--promote` 已校验源码指纹并更新 release。最新 EXE 46,108,490 字节，SHA-256 `88199a9ba872dc1c1af96376bb59b18946073a5a5af98d8917bb5bd54423ac44`；sidecar 一致。
- `frame/build`、`frame/dist`、`.pytest_cache`、源码 `__pycache__`、本轮 Pex runner 和构建生成的 `assets/app-icon.ico` 均清理。测试只用虚构账号与隔离 KDBX，没有触碰 `data/` 或 `release/data`。

这些工程回归不改变生产安全结论。外部 KeePassXC 等不遵守 Accnary 锁协议的客户端仍可能在最后内容检查与替换之间写入；同时编辑同一 KDBX 仍须避免。Python 托管内存清零、真实断电和第三方安全审计边界也仍在。

## 2026-10-26 主窗口内重新解锁

- 锁定后保留当前库路径，并在主窗口直接要求重新输入主密码；首次启动的选择/创建库流程不变。错密码留在锁定页显示错误，正确密码重新加载同一库。
- 锁定页状态下工作区和快捷键均不可用；敏感详情仍在切换页面前清空。新增真实 Qt 控件信号用例，覆盖锁定按钮、解锁按钮和 Enter 提交。
- 定向测试 `tests/audit/test_runtime.py`：10/10 通过。全量测试通过 Pex 调度 33 模块，239 passed、0 failed/errors/skipped。
- 已用固定脚本完成隔离构建、真实桌面启动 smoke、EXE `--check` 和 `--promote`。release EXE 为 46,112,129 字节，SHA-256 为 `5fb399239ce1e5aefa0dc7fdc292fdb5e2026a860ee6455734dce536146ef4f4`，sidecar 匹配。
- 构建中间目录、临时 runner、隔离 KDBX 和 Python/pytest 缓存均已清理。没有修改存储格式、账户模型、主密码策略或项目数据文件。

## 2026-10-26 分类切换闪动修复

- 中等宽度（760–999 px）点击分类不再自动收起侧栏；三栏可见状态只在布局状态实际变化时更新。窄屏选择分类后仍收起导航。
- Qt 点击回归验证 860 px 窗口切换分类时导航持续可见且 splitter 尺寸稳定；`tests/phase2/test_main_window.py` 9/9 通过。
- 全量测试通过 Pex 调度 33 个模块：240 passed、0 failed/errors/skipped。记录在 `docs/category-switch-20261026/pytest-results-full-20261026.txt`。
- 已完成固定构建、桌面启动 smoke、EXE `--check` 与 `--promote`。release EXE 为 46,110,496 字节，SHA-256 `d831bb955f6e181413967f028c12d742db67b044ac05fb79f212dc7b175c1500`，sidecar 一致。
- `build/`、`dist/`、缓存、临时 runner、生成 ICO 和测试临时 KDBX 均清理。

## 2026-10-26 分类 tooltip 清理

- 分类行移除了账户数悬浮提示，主题不再绘制点状焦点框；选中背景仍保留。回归断言确认分类项没有 tooltip；最终全量为 240 passed。
- 随后固定流程构建、真实桌面启动 smoke、release EXE `--check` 与 `--promote` 均通过。最新 EXE 为 46,110,897 字节，SHA-256 `b6cd0e8100ca9228239e0a0fdbbe29f34e08a836308e9d227ccda079e4a488be`，sidecar 匹配。
- 构建目录、`dist/`、缓存、临时 runner、生成 ICO 和测试临时 KDBX 均已清理。

## 2026-10-26 窄窗口分类切换二次修复

- 之前的点击测试只覆盖 860 逻辑像素。新增 535 逻辑像素测试后，旧实现复现了侧栏被收起的失败；分类点击现在保持侧栏打开，避免 splitter 和账户列表在指针下方换位。
- 535/860 两个宽度的 Qt 控件点击测试通过，splitter 尺寸保持不变，点击坐标不落到账户列表上，点击后 800 ms 未见 `QToolTip`。另用旧版窄屏收起路径验证：原点击坐标会落到账户列表有 tooltip 的记录上，解释了闪现小窗与布局跳变的关系；offscreen 测试不绘制真实桌面 tooltip。
- 全量回归：33 模块、241 passed、0 failed。报告：`docs/category-switch-repair-20261026/pytest-results-full-20261026.txt`。
- 已重建并 promote release EXE；真实窗口启动 smoke 与 EXE 自检通过。大小 46,109,272 字节，SHA-256 `337df629e5e7841c9275c5a0552acc5f31827081f373cbbda859d86e61c7fa00`，sidecar 匹配。

