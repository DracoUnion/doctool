# API / 接口文档

> 来源：《AI 时代程序员开发之道》第 2 章引言；《AI 时代架构师修炼之道》（接口设计）；《AI 时代-Python-金融大数据分析实战》第 3.4.3 节（API 调用 7 步）

---

## 接口总览

```markdown
# {{系统名}}API 接口文档

## 基础信息
| 字段 | 内容 |
|---|---|
| Base URL | {{https://api.example.com/v1}} |
| 认证方式 | {{Bearer Token / API Key}} |
| 数据格式 | {{JSON}} |

## 接口列表
| 接口 | 方法 | 路径 | 说明 |
|---|---|---|---|
| 用户登录 | POST | /auth/login | 获取 Token |
| 创建订单 | POST | /orders | 创建订单 |
```

## 单接口详情模板

```markdown
# 接口：{{接口名}}

## 请求
- 方法：{{POST}}
- 路径：{{/orders}}
- 请求头：{{Content-Type: application/json}}

### 请求参数
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| productId | string | 是 | 商品 ID |
| quantity | int | 是 | 数量，1~99 |

### 请求示例
{ "productId": "P001", "quantity": 2 }

## 响应
### 响应参数
| 参数 | 类型 | 说明 |
|---|---|---|
| code | int | 状态码 |
| data.orderId | string | 订单 ID |

### 响应示例
{ "code": 0, "data": { "orderId": "O20240001" } }

## 错误码
| code | 说明 |
|---|---|
| 0 | 成功 |
| 400 | 参数错误 |
| 401 | 未认证 |
```

## 接口调用 7 步流程

```
1. 注册获取 API Key
2. 了解 API 文档
3. 准备请求参数
4. 发送请求
5. 解析响应（JSON）
6. 错误处理
7. 保存/使用数据
```
