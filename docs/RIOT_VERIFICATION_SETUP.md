# Riot API 验证文件配置指南

## ❌ 问题原因

Riot 验证器无法访问 `https://github.com/JAMES9696/lolbot/riot.txt`，因为：
- GitHub 仓库 URL 返回的是 HTML 页面界面
- Riot 验证器需要纯文本内容
- `https://raw.githubusercontent.com/...` URL 可以返回纯文本，但 Riot 不接受这个域名

## ✅ 解决方案：启用 GitHub Pages

### 步骤 1: 启用 GitHub Pages

1. **访问仓库设置**:
   - 打开: https://github.com/JAMES9696/lolbot/settings/pages

2. **配置 GitHub Pages**:
   - **Source**: 选择 `Deploy from a branch`
   - **Branch**: 选择 `main` 分支
   - **Folder**: 选择 `/docs` 文件夹
   - 点击 **Save** 按钮

3. **等待部署**:
   - GitHub 会自动构建和部署（通常需要 1-2 分钟）
   - 部署完成后会显示: "Your site is live at https://james9696.github.io/lolbot/"

### 步骤 2: 验证文件可访问性

部署完成后，访问:
```
https://james9696.github.io/lolbot/riot.txt
```

应该看到纯文本内容：
```
127a696a-da4d-4cab-82f2-58b4379383eb
```

### 步骤 3: 更新 Riot Developer Portal 申请

回到 Riot Developer Portal 的申请表单：

1. **Product URL** 改为:
   ```
   https://james9696.github.io/lolbot/
   ```

2. **验证 URL**:
   - Riot 会尝试访问: `https://james9696.github.io/lolbot/riot.txt`
   - 点击 **"Verify URL"** 按钮

---

## 🔄 替代方案（如果 GitHub Pages 不可用）

### 方案 A: 使用 jsDelivr CDN

jsDelivr 可以将 GitHub 文件作为 CDN 提供：

**Product URL**:
```
https://cdn.jsdelivr.net/gh/JAMES9696/lolbot@main/
```

**验证 URL**:
```
https://cdn.jsdelivr.net/gh/JAMES9696/lolbot@main/riot.txt
```

### 方案 B: 部署到其他托管服务

如果你有其他 Web 托管服务（如 Netlify, Vercel, Cloudflare Pages），可以：

1. 将整个仓库部署到该服务
2. 确保 `riot.txt` 可以通过 `https://your-domain.com/riot.txt` 访问
3. 使用该域名作为 Product URL

---

## 📋 完整的申请流程检查清单

- [x] 创建 `riot.txt` 文件（内容: `127a696a-da4d-4cab-82f2-58b4379383eb`）
- [x] 推送到 GitHub 仓库根目录和 `docs/` 目录
- [ ] 启用 GitHub Pages（Source: `main` branch, Folder: `/docs`）
- [ ] 等待 GitHub Pages 部署完成（1-2 分钟）
- [ ] 验证 `https://james9696.github.io/lolbot/riot.txt` 可访问
- [ ] 更新 Riot Portal 的 Product URL 为 `https://james9696.github.io/lolbot/`
- [ ] 点击 **"Verify URL"** 按钮
- [ ] 提交 Production API Key 申请

---

## 🧪 测试验证

### 使用 curl 测试

```bash
# 测试 GitHub Pages URL（部署后）
curl https://james9696.github.io/lolbot/riot.txt

# 应该返回纯文本
# 127a696a-da4d-4cab-82f2-58b4379383eb
```

### 使用浏览器测试

1. 访问: https://james9696.github.io/lolbot/riot.txt
2. 确认浏览器显示的是纯文本，而不是 HTML
3. 确认内容只有一行: `127a696a-da4d-4cab-82f2-58b4379383eb`

---

## ⚠️ 常见问题

### Q: GitHub Pages 部署失败？
**A**: 检查：
- 仓库是否为公开（Public）
- `docs/riot.txt` 文件是否存在
- GitHub Actions 是否有权限（Settings → Actions → General → Workflow permissions）

### Q: 文件内容不正确？
**A**: 确保：
- 文件只包含验证码（无多余空格或换行）
- 文件编码为 UTF-8
- 文件名为小写 `riot.txt`

### Q: Riot 仍然无法验证？
**A**: 尝试：
1. 清除浏览器缓存
2. 等待 GitHub Pages CDN 更新（最多 10 分钟）
3. 使用 jsDelivr 替代方案
4. 联系 Riot Support

---

## 📚 参考链接

- [GitHub Pages 文档](https://docs.github.com/en/pages)
- [Riot Developer Portal](https://developer.riotgames.com/)
- [jsDelivr CDN](https://www.jsdelivr.com/)

---

**创建时间**: 2025-10-06
**状态**: 等待 GitHub Pages 部署
