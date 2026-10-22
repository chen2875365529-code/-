# PromptFloat · 桌面悬浮提示词面板

自建提示词库 + 图文混排 + 桌面置顶悬浮。纯 Python + Tkinter，零第三方依赖（除 Pillow），
不联网、不上传、所有数据都在你自己电脑上。

## 启动

双击 `启动 PromptFloat.bat`，或在 PowerShell 里跑：

```powershell
powershell -ExecutionPolicy Bypass -File "创建桌面快捷方式.ps1"
```

之后从桌面 `PromptFloat` 图标启动。想开机自动出现：

```powershell
powershell -ExecutionPolicy Bypass -File "设置开机自启.ps1"
```

取消自启：删掉 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PromptFloat.lnk`。

## 用法

| 操作 | 动作 |
| --- | --- |
| 鼠标单击卡片 | 复制这条提示词（文字 + 第一张图一起进剪贴板） |
| 双击卡片 | 编辑 |
| 双击缩略图 / 右键「查看大图」 | 大图预览，← → 翻页 |
| 右键卡片 | 复制 / 只看图 / 置顶 / 复制一份 / 删除 |
| 拖标题栏 | 移动面板，位置自动记忆 |
| 拖右下角 | 调整面板大小 |
| `+` | 新建提示词 |
| `-` | 收成悬浮球（球也能直接拖到任意位置） |
| `X` | 退出 |
| `Ctrl+Alt+P` | 全局热键，任何软件里都能把面板唤出/收起 |
| `Ctrl+F` / `Ctrl+N` / `Esc` | 搜索 / 新建 / 收起 |

编辑器里 `Ctrl+S` 保存，`Ctrl+Enter` 也保存。

## 图文一起复制

点卡片时，程序会同时往剪贴板写 **Unicode 文本** 和 **DIB 位图**：

- 粘到 ChatGPT / Claude / 微信 / Word → 文字和图片都能落进去
- 粘到只认纯文本的地方 → 拿到文字，不影响
- 只想发图 → 右键「只复制图片」

## 数据在哪

```
%APPDATA%\PromptFloat\
├─ prompts.json     提示词内容（纯 JSON，可手动改、可备份）
└─ images\          图片（导入时统一转 PNG 存本地）
```

备份就整个目录拷走。换电脑把目录拷回去即可。

## 已知边界

- 图片以「第一条」为卡片缩略图，多图在「查看大图」里逐张看。
- 富文本（加粗、颜色）不支持，正文是纯文本 —— 因为要保证粘到任何输入框都不炸。
- 首次运行窗口会出现在屏幕右上角，之后记住你拖到的位置。
- 150% / 200% 系统缩放下已做 Per-Monitor DPI 适配，不会糊。
