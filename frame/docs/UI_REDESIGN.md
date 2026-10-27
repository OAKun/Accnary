# Accnary Qt 工作空间与分类改版验收

日期：2026-10-25。改动限于 Qt 界面、分类展示/编辑及其回归测试和文档。没有修改 KDBX 引擎、账户数据模型、`Accnary.Meta` Schema、搜索匹配核心、固定打包配置或 `release/`。

## 本轮设计与实现

- 延续三栏工作空间：轻侧栏负责导航，中栏负责搜索与账号列表，右栏只展示当前账号。窗口宽度低于 1000 时侧栏收起到“分类”按钮；低于 760 时列表和详情改为单页切换，详情中 Ctrl+F 先返回列表再聚焦搜索框。
- 小窗口检查发现切换到详情后 QSplitter 仍把宽度留给隐藏列表，详情会变成零宽。已在响应式模式切换时分配分栏宽度并记住桌面分栏大小；回归测试确认窄屏详情可见、搜索热键返回可见搜索框。
- 顶部保留品牌、库名、锁定和设置；新建入口靠近列表；编辑与删除位于详情区；回收站和加密备份/恢复位于侧栏下方。收藏导航、星标和筛选已从 UI 移除，底层收藏字段及序列化仍保留。
- 列表以共享 `QStyledItemDelegate` 绘制，不为每条记录创建 QWidget；密码和 Token 不进入列表摘要、提示或搜索索引。详情只显示实际存在的分组，主要内容限制阅读宽度并可滚动。
- 编辑器将常用字段与平台/联系、登录/绑定、许可证、自定义字段分组；新增账户的分类只在编辑者明确选择后落盘。
- 浅色与深色沿用统一层级；中文字体、图标、控件高度与间距集中管理。未增加 WebView、联网图标、QML 或新依赖。

## 账号分类与旧库兼容

分类按账号的用途显示：社交与通讯、邮箱、科研与学术、开发与云服务、软件与工具、日常服务、设备与服务器、金融与支付，以及未分类。QQ、微信是普通账号记录，归入社交与通讯；它们不是独立验证步骤。邮箱或社交身份可继续作为其他账号的登录方式或绑定身份。

分类选择复用现有账号自定义字段 `主分类`，没有增加模型字段或 Schema 版本。读取旧库时仅将明确的旧分类/类型映射到新分类；对含义模糊的旧记录显示为未分类，不自动猜测、不写回。打开和普通编辑不保存推断结果；用户明确改变分类才保存该字段。受保护或未知值不会被分类界面静默覆盖，已有字段由现有 `Accnary.Meta` 兼容路径保存。

最近使用仍自动记录并作为列表排序方式；没有增加收藏替代项。全局搜索仍使用现有搜索服务，支持名称、账号、网址片段、长网址片段、邮箱、手机号和绑定身份；搜索覆盖所有分类并按相关性展示。

## 真实桌面操作与截图

下列桌面测试使用本机 Python、隔离的虚构 KDBX 和单独 QSettings 目录，没有打开真实密码库或改变 Windows 显示设置：

1. 600×560 窗口打开后点击 QQ 记录，详情显示账号、默认隐藏的密码和注册邮箱；Ctrl+F 回到列表并把焦点交给可见搜索框。
2. 粘贴虚构长网址 `https://studio.example.invalid/a/very/long/path?more=1#details`，搜索命中 Fictional Studio 一条记录。
3. 900×600 逻辑窗口、进程级 Qt 缩放 125% 下展开分类，社交与通讯列表同时显示 QQ、微信普通账号。
4. 自动渲染覆盖 QQ、复杂软件绑定/许可证、科研多网址、邮箱、新建/编辑账户、长网址搜索、无结果/空库/未选中、浅色/深色及窄窗口。

真实桌面截图：

- [三栏主窗口（真实桌面，900×600，Qt 125%）](../audit/ui-redesign-20261025/screenshots-purpose/desktop-900-dpi125.png)
- [社交分类中的 QQ 与微信（真实桌面）](../audit/ui-redesign-20261025/screenshots-purpose/desktop-900-social-category.png)
- [窄窗口 QQ 详情（真实桌面，600×560）](../audit/ui-redesign-20261025/screenshots-purpose/desktop-600-detail.png)
- [粘贴长网址后的真实搜索结果](../audit/ui-redesign-20261025/screenshots-purpose/desktop-600-search.png)

自动渲染截图（Windows Qt 后端中的真实 Qt 控件与服务数据，不是静态 mockup）：

- [浅色主窗口 / QQ](../audit/ui-redesign-20261025/screenshots-purpose/light-1.50-1220x850-qq.png)
- [复杂软件账号登录与绑定编辑](../audit/ui-redesign-20261025/screenshots-purpose/light-1.50-1220x850-edit-bindings.png)
- [科研多网址账户](../audit/ui-redesign-20261025/screenshots-purpose/light-1.50-1220x850-research.png)
- [长网址搜索结果](../audit/ui-redesign-20261025/screenshots-purpose/light-1.50-1220x850-search.png)
- [深色主窗口](../audit/ui-redesign-20261025/screenshots-purpose/dark-1.50-1220x850-qq.png)
- [600×560 窄屏详情](../audit/ui-redesign-20261025/screenshots-purpose/light-1.00-600x560-narrow-detail.png)

### 自动化验证

全量执行 29 个测试模块：**200 项通过，0 失败、0 错误、0 跳过**。另有 10 个浅色/深色、窗口尺寸与 Qt 缩放渲染任务均返回成功；KeePassXC 互操作回归包含在全量测试中。结果、JUnit 和逐任务日志见 [`audit/ui-redesign-20261025/acceptance-final/`](../audit/ui-redesign-20261025/acceptance-final/)；最终汇总见 [`acceptance.json`](../audit/ui-redesign-20261025/acceptance.json)。

主要新增/更新的覆盖包括：旧收藏值通过编辑器保存后保持不变、分类只读映射与显式保存、未知/受保护字段保护、QQ/微信分类列表、全分类长网址搜索、2500 条记录使用共享 delegate、锁定/切换主题时遮蔽秘密，以及小窗口详情与 Ctrl+F 响应式切换。

## 边界与仍需注意

- 这次没有构建或更新 EXE，因此改版只在源码运行版本中验证；release 中的旧 EXE 仍是此前界面。其 SHA-256 前后未变。
- Qt 进程级缩放验证不等于修改 Windows 系统 DPI，也未验证显示器热插拔或系统缩放设置切换。
- 600×560 下详情内容按设计纵向滚动，空间紧张时创建/修改时间等靠下内容需要滚动查看。
- 生产安全审计的残余风险保持原样；本轮 UI 验收不构成第三方安全认证，详见 [CODEX_AUDIT.md](CODEX_AUDIT.md)。
