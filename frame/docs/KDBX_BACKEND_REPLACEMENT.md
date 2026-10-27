# PyKeePass 替换可行性评估

时间：2026-10-27 12:54（Asia/Shanghai）

状态：完成源码检查和隔离兼容性探针；尚未替换应用后端、重编译或发布。

## 目标和边界

按用户决定，交付版本移除 PyKeePass，保留 Accnary 自有源码的非公开发布方式。
KDBX 是文件格式，不要求必须使用 PyKeePass；更换读写实现不等于必须迁移密码库。
目标继续采用现有 KDBX 4.0、主密码、AES-256 和 Argon2 策略，保留账户 Schema、UUID、历史、附件与未知数据。
不更改真实密码库或已有备份，不自行实现 AES、Argon2 等密码学算法。

## 当前依赖范围

- `app/storage/vault.py`：创建、解锁、加密写入、写后验证与主密码修改。
- `app/storage/backup.py`：备份内容验证及恢复验证。
- `app/services/catalog_service.py`：使用 Entry、Group、自定义属性、历史、回收站和 UUID。
- `main.py`、`Accnary.spec`、依赖锁定文件：运行检查、打包模板和依赖登记。
- 部分现有测试使用 PyKeePass 作为独立读取器；这与交付 EXE 的运行时依赖需要分别处理。

因此，删除 pip 包或只更改 import 会直接破坏现有程序。

## 候选初筛

| 候选 | 项目声明许可 | 适配考虑 |
| --- | --- | --- |
| [kdbxtool](https://github.com/coreyleavitt/kdbxtool) | Apache-2.0 | Python；元数据标注 Alpha；需独立验证保存语义，不能直接相信功能声明 |
| [kdbxweb](https://github.com/keeweb/kdbxweb) | MIT | JavaScript/TypeScript；接入现有 Qt/Python 应用需要额外运行时或桥接 |
| [keepass-rs](https://github.com/sseemayer/keepass-rs) | MIT | Rust；项目把 KDBX 写入标注为 experimental，不作为当前直接替换首选 |

以上仅为项目自身许可初筛，正式交付仍须核对实际引入的传递依赖、许可证和声明材料。

## kdbxtool 实测

检查了 PyPI 0.1.7 和 Git 提交 `06d15e38713387e50be2de26698794e75f7b08c9`。
PyPI wheel SHA-256：`48c8d5c6499514ff59bd75e29c8714cacfb32bbf178bac10394ce571b29df645`。

全部使用新创建的虚构凭据 KDBX，数据包括自定义 JSON、受保护字段、UUID、一条历史、一份附件以及组和账户中的未知 XML 节点。
PyKeePass 只用作本次探针的旧格式样本生成器和独立读取对照，没有把它新增到任何交付组件。

| 检查 | PyPI 0.1.7 高层 API | 上述 Git 提交高层 API |
| --- | --- | --- |
| 读取账号、密码、自定义 JSON、UUID | 通过 | 通过 |
| 保存后账号密码、JSON、历史数量、附件数量 | 通过 | 通过 |
| 组和账户的未知 XML 节点保留 | 失败：两类节点均丢失 | 失败：两类节点均丢失 |
| 保持原 KDBX 4.0 文件版本 | 失败：写为 4.1 | 失败：写为 4.1 |
| 保存后用原读取器打开文件 | 通过 | 通过 |
| 原读取器读取保存后的创建时间 | 失败：`struct.error` | 失败：`struct.error` |

对应源码位置：`database.py::_build_xml` 重新构建 XML，`database.py::_encode_time` 输出 ISO 时间，`parsing/header.py::KdbxHeader.to_bytes` 固定写入 4.1。
不能把“账号密码能读回来”描述为完整兼容，也不能把时间读取失败描述为整个文件无法解锁。

复现要点：在虚构 KDBX 的 Group/Entry 中各加入非标准 XML 节点并保存；调用 `Database.open(...).save(new_path)`；重开新文件，检查未知节点、头部版本和账户创建时间。两个版本均出现上述问题。

## 底层接口验证与实施方向

另外针对上述 Git 提交做了一次范围有限的底层读写验证：使用 `read_kdbx4` / `write_kdbx4`，保留原 XML 和附件，适配头部序列化为 4.0（在计算头部校验和、HMAC 之前），更新外层随机种子、IV 和 KDF 盐。

结果：KDBX 4.0 保持、解密后完整 XML 的规范化比较、全部附件字节、UUID、密码、创建时间、KDF 类型与参数均通过；错误密码和被篡改的文件均被拒绝。
这仅证明“保留 XML 的后端适配”有可行基础，不是新的生产后端验收。
由于探针没有编辑 XML，保留了原内层保护流；正式编辑保存必须完整处理内层保护流的随机密钥更新和所有受保护值，不能直接复用这个只读往返探针。

后续实施应建立 Accnary 自有的 KDBX 文档适配层，继续复用已有安全保存、备份、冲突检测和会话管理；UI 与账户 Schema 保持稳定。
必须额外覆盖未知外层/内层头字段、未知 XML、KDF 版本、KDBX 3.x 只读和 4.1 拒写保护、历史/附件/回收站、复杂账户、主密码轮换及失败回滚。
若底层实现不能满足这些要求，应更换候选；不得为了去掉依赖而降低数据安全保证或偷偷升级文件格式。

## 当前交付状态

本次仅新增本文档。应用源码和依赖环境未切换，现有 EXE 仍使用 PyKeePass，不能称为已经完成移除。
现有 EXE SHA-256 保持 `70f6d28aefcf493ccf44245fd1b2088424a71ab9aec3c363d558e189ccc62c21`。
没有运行主程序完整回归，不能沿用旧版测试结果为新后端背书。
隔离下载、样本与探针产物完成记录后清理；运行探针使用 `-B`，不生成 Python 缓存。
