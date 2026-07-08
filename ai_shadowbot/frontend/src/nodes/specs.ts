// ai-shadowbot 工作流节点规格定义
// 字段约定参考 Alpha Node node_defs/*.json：
//   - kind: 节点种类（注册为 LiteGraph 'ai/<kind>'）
//   - node_type: 后端 NodeType（start/end/atomic/condition/loop/wait）
//   - 原子动作(atomic) 的 params 含 atomic_action 字段，由 converter 自动注入
//   - widget 顺序即序列化顺序，converter 按 index 映射回 params

export type WidgetType = 'number' | 'text' | 'combo' | 'toggle'

export interface WidgetSpec {
  name: string
  type: WidgetType
  default: any
  options?: string[]
}

export interface NodeSpec {
  kind: string
  category: string
  label: string
  node_type: string
  inputs: string[]
  outputs: string[]
  widgets: WidgetSpec[]
}

export const NODE_SPECS: NodeSpec[] = [
  { kind: 'start', category: '控制', label: '开始', node_type: 'start', inputs: [], outputs: [''], widgets: [] },
  { kind: 'end', category: '控制', label: '结束', node_type: 'end', inputs: [''], outputs: [], widgets: [] },
  { kind: 'wait', category: '系统', label: '等待', node_type: 'wait', inputs: [''], outputs: [''], widgets: [{ name: 'seconds', type: 'number', default: 1.0 }] },
  { kind: 'click', category: '鼠标', label: '点击', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'x', type: 'number', default: 0 }, { name: 'y', type: 'number', default: 0 }] },
  { kind: 'double_click', category: '鼠标', label: '双击', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'x', type: 'number', default: 0 }, { name: 'y', type: 'number', default: 0 }] },
  { kind: 'right_click', category: '鼠标', label: '右键单击', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'x', type: 'number', default: 0 }, { name: 'y', type: 'number', default: 0 }] },
  { kind: 'scroll', category: '鼠标', label: '滚动', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'dx', type: 'number', default: 0 }, { name: 'dy', type: 'number', default: 0 }] },
  { kind: 'type_text', category: '键盘', label: '输入文本', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'text', type: 'text', default: '' }] },
  { kind: 'key_press', category: '键盘', label: '按键', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'key', type: 'text', default: 'enter' }] },
  { kind: 'open_app', category: '应用', label: '打开应用', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'name', type: 'text', default: '' }] },
  { kind: 'screenshot', category: '系统', label: '截图', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [] },
  { kind: 'condition', category: '控制', label: '条件判断', node_type: 'condition', inputs: [''], outputs: ['true', 'false'], widgets: [{ name: 'expression', type: 'text', default: '' }] },
  { kind: 'loop', category: '控制', label: '循环', node_type: 'loop', inputs: [''], outputs: [''], widgets: [{ name: 'loop_type', type: 'combo', default: 0, options: ['while', 'for', 'foreach'] }, { name: 'condition', type: 'text', default: '' }, { name: 'max_iterations', type: 'number', default: 100 }] },
  // === 浏览器节点 ===
  { kind: 'browser_navigate', category: '浏览器', label: '打开网页', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'url', type: 'text', default: '' }] },
  { kind: 'browser_click', category: '浏览器', label: '点击元素', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'x', type: 'number', default: 0 }, { name: 'y', type: 'number', default: 0 }] },
  { kind: 'browser_type', category: '浏览器', label: '输入文本', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'text', type: 'text', default: '' }] },
  { kind: 'browser_screenshot', category: '浏览器', label: '网页截图', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [] },
  { kind: 'browser_wait', category: '浏览器', label: '等待', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'seconds', type: 'number', default: 1.0 }] },
  { kind: 'browser_scroll', category: '浏览器', label: '滚动页面', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'dx', type: 'number', default: 0 }, { name: 'dy', type: 'number', default: 0 }] },
  // === Excel 节点 ===
  { kind: 'excel_read', category: 'Excel', label: '读取Excel/CSV', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'path', type: 'text', default: '' }, { name: 'column', type: 'text', default: '' }, { name: 'value', type: 'text', default: '' }] },
  { kind: 'excel_write', category: 'Excel', label: '写入Excel/CSV', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'path', type: 'text', default: '' }, { name: 'sheet', type: 'text', default: 'Sheet1' }] },
  // === 网络节点 ===
  { kind: 'http_request', category: '网络', label: 'HTTP请求', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'method', type: 'combo', default: 'GET', options: ['GET', 'POST', 'PUT', 'DELETE'] }, { name: 'url', type: 'text', default: '' }] },
  { kind: 'http_get', category: '网络', label: 'GET请求', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'url', type: 'text', default: '' }] },
  { kind: 'http_post', category: '网络', label: 'POST请求', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'url', type: 'text', default: '' }, { name: 'body', type: 'text', default: '' }] },
  { kind: 'http_put', category: '网络', label: 'PUT请求', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'url', type: 'text', default: '' }, { name: 'body', type: 'text', default: '' }] },
  { kind: 'http_delete', category: '网络', label: 'DELETE请求', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'url', type: 'text', default: '' }] },
  // === 文件节点 ===
  { kind: 'fs_read', category: '文件', label: '读取文件', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'path', type: 'text', default: '' }] },
  { kind: 'fs_write', category: '文件', label: '写入文件', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'path', type: 'text', default: '' }, { name: 'content', type: 'text', default: '' }] },
  { kind: 'fs_delete', category: '文件', label: '删除文件', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'path', type: 'text', default: '' }] },
  { kind: 'fs_list', category: '文件', label: '列出目录', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'path', type: 'text', default: '' }] },
  { kind: 'fs_exists', category: '文件', label: '检查是否存在', node_type: 'atomic', inputs: [''], outputs: [''], widgets: [{ name: 'path', type: 'text', default: '' }] },
]

export const SPEC_BY_KIND: Record<string, NodeSpec> = Object.fromEntries(
  NODE_SPECS.map((s) => [s.kind, s]),
)
