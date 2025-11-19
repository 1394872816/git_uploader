import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import subprocess
import os
import threading
import json
from pathlib import Path
import re

class GitUploader:
    def __init__(self, root):
        self.root = root
        self.root.title("GitHub 自动上传工具 v5.0")
        self.root.geometry("800x750")
        
        # 防止窗口关闭时程序卡死
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.config_file = self.get_config_path()
        
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.main_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.main_frame, text='上传工具')
        
        self.config_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.config_frame, text='Git 配置')
        
        self.help_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.help_frame, text='使用帮助')
        
        self.setup_main_ui()
        self.setup_config_ui()
        self.setup_help_ui()
        self.load_config()
        self.check_git_config()
    
    def on_closing(self):
        """窗口关闭时的处理"""
        if messagebox.askokcancel("退出", "确定要退出吗？"):
            self.root.quit()
            self.root.destroy()
    
    def get_config_path(self):
        """获取配置文件路径"""
        try:
            script_dir = Path(__file__).parent
            config_path = script_dir / "git_uploader_config.json"
            config_path.touch(exist_ok=True)
            return str(config_path)
        except:
            home_dir = Path.home()
            return str(home_dir / "git_uploader_config.json")
    
    def is_ssh_url(self, url):
        """判断是否是 SSH URL"""
        return url.strip().startswith('git@')
    
    def is_https_url(self, url):
        """判断是否是 HTTPS URL"""
        return url.strip().startswith('https://')
    
    def convert_url_to_ssh(self, url):
        """将 HTTPS URL 转换为 SSH"""
        url = url.strip()
        if 'github.com' in url:
            url = url.replace('https://github.com/', 'git@github.com:')
            url = url.replace('http://github.com/', 'git@github.com:')
        return url
    
    def convert_url_to_https(self, url):
        """将 SSH URL 转换为 HTTPS"""
        url = url.strip()
        if url.startswith('git@github.com:'):
            url = url.replace('git@github.com:', 'https://github.com/')
        return url
    
    def normalize_git_url(self, url):
        """规范化 Git URL"""
        url = url.strip()
        if not url:
            return url
        url = url.rstrip('/')
        if not url.endswith('.git'):
            url += '.git'
        return url
    
    def get_correct_url(self):
        """获取正确格式的 URL"""
        url = self.normalize_git_url(self.git_url.get())
        connection_type = self.connection_type.get()
        
        if connection_type == "ssh" and not self.is_ssh_url(url):
            self.log("⚠️ 地址格式与连接方式不匹配，自动转换为 SSH 格式")
            url = self.convert_url_to_ssh(url)
            self.git_url.set(url)
        elif connection_type == "https" and not self.is_https_url(url):
            self.log("⚠️ 地址格式与连接方式不匹配，自动转换为 HTTPS 格式")
            url = self.convert_url_to_https(url)
            self.git_url.set(url)
        
        return url
    
    def sanitize_commit_message(self, message):
        """清理提交信息中的特殊字符"""
        # 移除可能导致命令执行问题的字符
        message = message.replace('"', '\\"')  # 转义双引号
        message = message.replace('`', '\\`')  # 转义反引号
        message = message.replace('$', '\\$')  # 转义美元符号
        return message
    
    def check_git_installed(self):
        """检查 Git 是否安装"""
        try:
            result = subprocess.run(['git', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.strip()
                self.log(f"✅ {version}")
                return True
            return False
        except FileNotFoundError:
            self.log("❌ Git 未安装")
            messagebox.showerror(
                "Git 未安装",
                "未检测到 Git！\n\n"
                "请先安装 Git：\n"
                "Windows: https://git-scm.com/download/win\n"
                "Mac: brew install git\n"
                "Linux: sudo apt install git"
            )
            return False
    
    def fix_ssh_known_hosts(self):
        """修复 SSH known_hosts 问题"""
        self.log("🔧 正在修复 SSH 连接...")
        
        # 添加 GitHub 到 known_hosts
        success, _, _ = self.run_command(
            'ssh-keyscan github.com >> "%USERPROFILE%\\.ssh\\known_hosts" 2>nul',
            show_output=False
        )
        
        if success:
            self.log("✅ SSH 主机密钥已添加")
            return True
        else:
            # 尝试 Linux/Mac 方式
            success, _, _ = self.run_command(
                'ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null',
                show_output=False
            )
            if success:
                self.log("✅ SSH 主机密钥已添加")
                return True
        
        return False
    
    def check_ssh_configured(self):
        """检查 SSH 是否已配置"""
        home = Path.home()
        ssh_key = home / '.ssh' / 'id_rsa'
        
        if not ssh_key.exists():
            return False, "SSH 密钥不存在"
        
        success, output, error = self.run_command(
            "ssh -T git@github.com -o StrictHostKeyChecking=no",
            check_error=False,
            show_output=False
        )
        
        if "successfully authenticated" in output or "successfully authenticated" in error:
            return True, "SSH 已配置"
        elif "Permission denied" in error:
            return False, "SSH 密钥未添加到 GitHub"
        else:
            return False, "SSH 连接失败"
    
    def check_disk_space(self, path):
        """检查磁盘空间"""
        try:
            if os.path.exists(path):
                stat = os.statvfs(path) if hasattr(os, 'statvfs') else None
                if stat:
                    free_space = stat.f_bavail * stat.f_frsize / (1024**3)  # GB
                    if free_space < 0.1:  # 小于100MB
                        self.log(f"⚠️ 磁盘空间不足：剩余 {free_space:.2f} GB")
                        return False
            return True
        except:
            return True  # 无法检测则假设正常
    
    def setup_main_ui(self):
        """设置主界面"""
        frame = self.main_frame
        
        # 仓库路径
        ttk.Label(frame, text="本地仓库路径:").grid(row=0, column=0, padx=10, pady=10, sticky='w')
        self.repo_path = tk.StringVar()
        ttk.Entry(frame, textvariable=self.repo_path, width=50).grid(row=0, column=1, padx=10, pady=10)
        ttk.Button(frame, text="浏览", command=self.browse_folder).grid(row=0, column=2, padx=5)
        
        # 连接方式
        ttk.Label(frame, text="连接方式:").grid(row=1, column=0, padx=10, pady=5, sticky='w')
        conn_frame = ttk.Frame(frame)
        conn_frame.grid(row=1, column=1, sticky='w', padx=10)
        
        self.connection_type = tk.StringVar(value="ssh")
        ttk.Radiobutton(conn_frame, text="SSH (推荐)", variable=self.connection_type, 
                       value="ssh", command=self.on_connection_change).pack(side='left', padx=5)
        ttk.Radiobutton(conn_frame, text="HTTPS", variable=self.connection_type, 
                       value="https", command=self.on_connection_change).pack(side='left', padx=5)
        
        # GitHub 仓库地址
        ttk.Label(frame, text="仓库地址:").grid(row=2, column=0, padx=10, pady=10, sticky='w')
        self.git_url = tk.StringVar()
        self.url_entry = ttk.Entry(frame, textvariable=self.git_url, width=50)
        self.url_entry.grid(row=2, column=1, padx=10, pady=10, columnspan=2, sticky='ew')
        self.url_entry.bind('<KeyRelease>', self.on_url_input)
        
        # URL 状态提示
        url_info_frame = ttk.Frame(frame)
        url_info_frame.grid(row=3, column=1, sticky='w', padx=10)
        
        self.url_example = ttk.Label(url_info_frame, text="", font=('Arial', 8), foreground='gray')
        self.url_example.pack(side='left')
        
        self.url_status = ttk.Label(url_info_frame, text="", font=('Arial', 8, 'bold'))
        self.url_status.pack(side='left', padx=10)
        
        self.update_url_example()
        
        # GitHub Token
        ttk.Label(frame, text="GitHub Token:").grid(row=4, column=0, padx=10, pady=5, sticky='w')
        self.github_token = tk.StringVar()
        self.token_entry = ttk.Entry(frame, textvariable=self.github_token, width=50, show="*")
        self.token_entry.grid(row=4, column=1, padx=10, pady=5, columnspan=2, sticky='ew')
        
        token_btn_frame = ttk.Frame(frame)
        token_btn_frame.grid(row=5, column=1, sticky='w', padx=10)
        
        self.token_help = ttk.Label(token_btn_frame, text="获取 Token", 
                                    font=('Arial', 8), foreground='blue', cursor="hand2")
        self.token_help.pack(side='left')
        self.token_help.bind("<Button-1>", lambda e: self.open_token_page())
        
        ttk.Label(token_btn_frame, text=" | ", font=('Arial', 8)).pack(side='left')
        
        self.token_test = ttk.Label(token_btn_frame, text="测试 Token", 
                                    font=('Arial', 8), foreground='blue', cursor="hand2")
        self.token_test.pack(side='left')
        self.token_test.bind("<Button-1>", lambda e: self.test_token())
        
        ttk.Label(token_btn_frame, text=" (仅 HTTPS 需要)", 
                 font=('Arial', 8), foreground='gray').pack(side='left')
        
        # 分支名称
        ttk.Label(frame, text="分支名称:").grid(row=6, column=0, padx=10, pady=10, sticky='w')
        self.branch = tk.StringVar(value="main")
        branch_entry = ttk.Entry(frame, textvariable=self.branch, width=30)
        branch_entry.grid(row=6, column=1, padx=10, pady=10, sticky='w')
        ttk.Button(frame, text="检测远程分支", command=self.detect_remote_branch).grid(row=6, column=1, padx=200, sticky='w')
        
        # 提交信息
        ttk.Label(frame, text="提交信息:").grid(row=7, column=0, padx=10, pady=10, sticky='nw')
        self.commit_msg = tk.Text(frame, height=3, width=50)
        self.commit_msg.grid(row=7, column=1, padx=10, pady=10, columnspan=2, sticky='ew')
        
        # 文件选择
        ttk.Label(frame, text="提交文件:").grid(row=8, column=0, padx=10, pady=10, sticky='w')
        self.file_pattern = tk.StringVar(value=".")
        ttk.Entry(frame, textvariable=self.file_pattern, width=50).grid(row=8, column=1, padx=10, pady=10, columnspan=2, sticky='ew')
        
        # 操作按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=9, column=0, columnspan=3, pady=15)
        
        ttk.Button(btn_frame, text="🚀 一键上传", command=self.full_workflow, width=14).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="初始化", command=self.init_repo, width=10).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="提交", command=self.commit_only, width=10).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="推送", command=self.push_only, width=10).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="检查状态", command=self.check_status, width=12).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="保存配置", command=self.save_config, width=10).pack(side='left', padx=5)
        
        # 日志输出
        ttk.Label(frame, text="执行日志:").grid(row=10, column=0, padx=10, pady=10, sticky='nw')
        
        # 添加清空日志按钮
        log_header_frame = ttk.Frame(frame)
        log_header_frame.grid(row=10, column=1, columnspan=2, sticky='e', padx=10)
        ttk.Button(log_header_frame, text="清空日志", command=self.clear_log, width=10).pack()
        
        self.log_text = scrolledtext.ScrolledText(frame, height=12, width=85, state='disabled')
        self.log_text.grid(row=11, column=0, columnspan=3, padx=10, pady=5, sticky='nsew')
        
        # 进度条
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.grid(row=12, column=0, columnspan=3, padx=10, pady=10, sticky='ew')
        
        frame.grid_rowconfigure(11, weight=1)
        frame.grid_columnconfigure(1, weight=1)
    
    def clear_log(self):
        """清空日志"""
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
    
    def on_connection_change(self):
        """连接方式改变"""
        self.update_url_example()
        self.check_url_format()
        
        url = self.git_url.get().strip()
        if url:
            if self.connection_type.get() == "ssh" and self.is_https_url(url):
                new_url = self.convert_url_to_ssh(url)
                self.git_url.set(new_url)
                self.log(f"✓ 已转换为 SSH 格式: {new_url}")
            elif self.connection_type.get() == "https" and self.is_ssh_url(url):
                new_url = self.convert_url_to_https(url)
                self.git_url.set(new_url)
                self.log(f"✓ 已转换为 HTTPS 格式: {new_url}")
    
    def on_url_input(self, event=None):
        """URL 输入检查"""
        self.check_url_format()
    
    def check_url_format(self):
        """检查 URL 格式"""
        url = self.git_url.get().strip()
        if not url:
            self.url_status.config(text="", foreground="black")
            return
        
        connection_type = self.connection_type.get()
        
        if connection_type == "ssh":
            if self.is_ssh_url(url):
                self.url_status.config(text="✓ 格式正确", foreground="green")
            else:
                self.url_status.config(text="⚠ 格式错误", foreground="red")
        else:
            if self.is_https_url(url):
                self.url_status.config(text="✓ 格式正确", foreground="green")
            else:
                self.url_status.config(text="⚠ 格式错误", foreground="red")
    
    def update_url_example(self):
        """更新示例"""
        if self.connection_type.get() == "ssh":
            self.url_example.config(text="格式: git@github.com:用户名/仓库名.git")
            if hasattr(self, 'token_entry'):
                self.token_entry.config(state='disabled')
        else:
            self.url_example.config(text="格式: https://github.com/用户名/仓库名.git")
            if hasattr(self, 'token_entry'):
                self.token_entry.config(state='normal')
    
    def setup_config_ui(self):
        """设置配置界面"""
        frame = self.config_frame
        
        ttk.Label(frame, text="Git 全局配置", font=('Arial', 14, 'bold')).pack(pady=20)
        
        config_inner = ttk.Frame(frame)
        config_inner.pack(padx=20, pady=10, fill='x')
        
        ttk.Label(config_inner, text="用户名:").grid(row=0, column=0, padx=10, pady=10, sticky='w')
        self.git_username = tk.StringVar()
        ttk.Entry(config_inner, textvariable=self.git_username, width=40).grid(row=0, column=1, padx=10, pady=10)
        
        ttk.Label(config_inner, text="邮箱:").grid(row=1, column=0, padx=10, pady=10, sticky='w')
        self.git_email = tk.StringVar()
        ttk.Entry(config_inner, textvariable=self.git_email, width=40).grid(row=1, column=1, padx=10, pady=10)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=20)
        
        ttk.Button(btn_frame, text="保存配置", command=self.save_git_config, width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="检查配置", command=self.check_git_config, width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="配置 SSH", command=self.setup_ssh_guide, width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="测试 SSH", command=self.test_ssh, width=15).pack(side='left', padx=5)
        
        ttk.Label(frame, text="当前配置:").pack(pady=10)
        self.config_display = scrolledtext.ScrolledText(frame, height=20, width=70, state='disabled')
        self.config_display.pack(padx=20, pady=10)
    
    def setup_help_ui(self):
        """设置帮助界面"""
        frame = self.help_frame
        
        help_text = """
╔══════════════════════════════════════════════════════════════╗
║              GitHub 自动上传工具 - 使用指南                    ║
╚══════════════════════════════════════════════════════════════╝


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 快速开始（两种方式任选其一）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────────────────────────────────────────┐
│ 方式一：SSH（⭐ 强烈推荐）                                    │
│ 优点：一次配置永久使用，无需记住密码                           │
└─────────────────────────────────────────────────────────────┘

🔸 第一步：在 Git 配置页面填写你的信息
   ├─ 用户名：填写你的 GitHub 用户名（如：zhangsan）
   ├─ 邮箱：填写你的邮箱（如：zhangsan@example.com）
   └─ 点击"保存配置"

🔸 第二步：配置 SSH
   ├─ 点击"Git 配置"页面的"配置 SSH"按钮
   ├─ 在弹出的向导中点击"自动配置 SSH"
   ├─ 公钥会自动复制到剪贴板
   ├─ 浏览器会自动打开 GitHub SSH 设置页
   └─ 在 GitHub 页面粘贴公钥，点击添加

🔸 第三步：使用
   ├─ 连接方式：选择"SSH (推荐)"
   ├─ 仓库地址：git@github.com:你的用户名/仓库名.git
   ├─ 填写提交信息
   └─ 点击"🚀 一键上传"

   ✅ 完成！以后每次上传都不需要输入密码


┌─────────────────────────────────────────────────────────────┐
│ 方式二：HTTPS + Token                                         │
│ 优点：配置简单，适合临时使用                                   │
└─────────────────────────────────────────────────────────────┘

🔸 第一步：生成 Token
   ├─ 点击主界面的"获取 Token"链接
   ├─ 或访问：https://github.com/settings/tokens/new
   ├─ Note 填写：git_uploader（随便填）
   ├─ Expiration 选择：90 days（或更长）
   ├─ 勾选权限：✓ repo（展开并全选所有子项）
   ├─ 点击底部绿色按钮"Generate token"
   └─ ⚠️ 立即复制 Token（只显示一次！）

🔸 第二步：使用
   ├─ 连接方式：选择"HTTPS"
   ├─ 仓库地址：https://github.com/你的用户名/仓库名.git
   ├─ GitHub Token：粘贴刚才复制的 Token
   ├─ 填写提交信息
   └─ 点击"🚀 一键上传"


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 详细步骤（新手必看）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【SSH 配置详细步骤】

① 打开命令行工具
   • Windows：按 Win + R，输入 cmd 或 powershell，回车
   • Mac/Linux：打开 Terminal

② 生成 SSH 密钥（首次使用需要）
   复制粘贴以下命令，回车执行：
   
   ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
   
   遇到提示时：
   • Enter file... → 直接按回车
   • Enter passphrase... → 直接按回车（不设密码）
   • Enter same passphrase... → 再按回车

③ 查看公钥
   Windows 执行：
   type %USERPROFILE%\\.ssh\\id_rsa.pub
   
   Mac/Linux 执行：
   cat ~/.ssh/id_rsa.pub
   
   复制显示的全部内容（从 ssh-rsa 开始）

④ 添加到 GitHub
   • 访问：https://github.com/settings/ssh/new
   • Title：随便填（如：My-Computer）
   • Key：粘贴刚才复制的内容
   • 点击"Add SSH key"按钮
   • 输入 GitHub 密码确认

⑤ 测试连接
   • 回到工具的"Git 配置"页面
   • 点击"测试 SSH"按钮
   • 看到"✅ SSH 配置正确"即成功


【HTTPS Token 配置详细步骤】

① 登录 GitHub
   访问：https://github.com/settings/tokens/new

② 填写 Token 信息
   • Note：git_uploader（备注，随便填）
   • Expiration：90 days（有效期，建议选长一点）
   • Select scopes：勾选以下权限
     ✓ repo（必须！展开勾选所有子项）
       ✓ repo:status
       ✓ repo_deployment
       ✓ public_repo
       ✓ repo:invite
       ✓ security_events

③ 生成 Token
   • 滚动到页面底部
   • 点击绿色按钮"Generate token"
   • ⚠️ 立即复制 Token（格式：ghp_xxxxxxxxxxxx）
   • ⚠️ 只显示一次，关闭页面就看不到了！

④ 使用 Token
   • 在工具中选择"HTTPS"连接方式
   • 将 Token 粘贴到"GitHub Token"输入框
   • 点击"测试 Token"验证是否有效


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 仓库地址格式说明
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【如何获取仓库地址】

方法1：从 GitHub 仓库页面获取
  ① 打开你的 GitHub 仓库页面
  ② 点击绿色的"Code"按钮
  ③ 选择"SSH"或"HTTPS"标签
  ④ 复制显示的地址

方法2：手动拼接
  格式：
  • SSH：   git@github.com:用户名/仓库名.git
  • HTTPS： https://github.com/用户名/仓库名.git
  
  示例：
  假设用户名是 zhangsan，仓库名是 my-project
  • SSH：   git@github.com:zhangsan/my-project.git
  • HTTPS： https://github.com/zhangsan/my-project.git


【常见地址格式错误】

❌ 错误示例：
  https://github.com/zhangsan/my-project     （缺少 .git）
  https://github.com/zhangsan/my-project/    （多了斜杠）
  github.com/zhangsan/my-project.git         （缺少协议）
  
✅ 正确示例：
  SSH：   git@github.com:zhangsan/my-project.git
  HTTPS： https://github.com/zhangsan/my-project.git

💡 提示：工具会自动检测并修正常见格式错误！


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❓ 常见问题解答
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Q1：首次使用推荐用哪种方式？
A1：推荐 SSH 方式
    • 配置一次，永久使用
    • 不需要记住密码
    • 更安全
    • 唯一缺点：首次配置稍微复杂（但工具有自动向导）

Q2：SSH 和 HTTPS 有什么区别？
A2：
    ┌──────────┬────────────┬────────────┐
    │          │    SSH     │   HTTPS    │
    ├──────────┼────────────┼────────────┤
    │ 配置难度 │ 稍复杂     │ 简单       │
    │ 是否需要 │ 不需要     │ 需要Token  │
    │ 安全性   │ 很高       │ 高         │
    │ 推荐度   │ ⭐⭐⭐⭐⭐ │ ⭐⭐⭐     │
    └──────────┴────────────┴────────────┘

Q3：Token 过期了怎么办？
A3：重新生成一个新的 Token
    • 访问：https://github.com/settings/tokens
    • 找到旧的 Token，点击删除
    • 重新生成新的 Token
    • 更新到工具中

Q4：忘记保存 Token 怎么办？
A4：Token 只显示一次，忘记了只能重新生成
    • 建议：生成后立即保存到安全的地方
    • 或在工具中点击"保存配置"

Q5：推送失败怎么办？
A5：根据错误提示：
    • "Host key verification failed"
      → SSH 首次连接，工具会自动修复
    
    • "Permission denied (publickey)"
      → SSH 密钥未添加到 GitHub
      → 点击"配置 SSH"按钮重新配置
    
    • "403 Forbidden"
      → Token 无效或权限不足
      → 重新生成 Token，确保勾选 repo 权限
    
    • "rejected" 或 "non-fast-forward"
      → 远程仓库有新的提交
      → 工具会提示选择拉取合并或强制推送

Q6：如何验证配置是否成功？
A6：
    • SSH 方式：点击"测试 SSH"按钮
    • HTTPS 方式：点击"测试 Token"按钮
    • 看到"✅ 成功"提示即配置正确

Q7：可以同时配置 SSH 和 HTTPS 吗？
A7：可以，但每次只能用一种方式
    • 通过"连接方式"单选框切换
    • 工具会自动转换仓库地址格式

Q8：分支名称应该填什么？
A8：
    • 新仓库通常是 main
    • 老仓库可能是 master
    • 点击"检测远程分支"按钮自动获取


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 功能按钮说明
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【主界面按钮】

🚀 一键上传
   • 功能：自动完成 初始化 → 添加 → 提交 → 推送 全流程
   • 适合：新手、懒人、快速上传
   • 推荐：⭐⭐⭐⭐⭐

初始化
   • 功能：设置远程仓库地址和分支
   • 适合：首次使用某个仓库
   • 等同于：git init + git remote add

提交
   • 功能：只提交到本地仓库
   • 适合：想先本地保存，稍后再推送
   • 等同于：git add + git commit

推送
   • 功能：将本地已提交的内容推送到 GitHub
   • 适合：本地已有提交，只需推送
   • 等同于：git push

检查状态
   • 功能：查看当前仓库状态、分支、提交历史
   • 适合：想了解仓库当前情况
   • 等同于：git status + git log

保存配置
   • 功能：保存当前设置（路径、地址、Token等）
   • 适合：常用仓库，下次自动加载


【Git 配置页面】

保存配置
   • 保存用户名和邮箱到 Git 全局配置

检查配置
   • 查看当前 Git 全局配置

配置 SSH
   • 打开 SSH 配置向导
   • 一键完成 SSH 密钥生成和配置

测试 SSH
   • 验证 SSH 是否配置正确
   • 测试能否连接 GitHub


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 注意事项
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【安全提醒】

🔐 Token 安全
   • Token 等同于密码，不要分享给任何人
   • 不要将 Token 提交到 Git 仓库
   • Token 泄露后立即到 GitHub 删除
   • 建议定期更换 Token

🔑 SSH 密钥安全
   • 私钥文件（id_rsa）要妥善保管
   • 不要上传私钥到任何地方
   • 公钥（id_rsa.pub）可以公开
   • 私钥丢失需重新生成


【使用建议】

✅ 推荐做法
   • 使用 SSH 方式（一劳永逸）
   • 定期提交代码（养成好习惯）
   • 写清楚提交信息（便于回溯）
   • 推送前点击"检查状态"
   • 保存配置（下次更方便）

❌ 不推荐做法
   • 在公共电脑上保存 Token
   • 使用简单的提交信息（如：update、修改等）
   • 长期不提交（容易冲突）
   • 直接删除 .git 文件夹（会丢失历史）


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📞 获取帮助
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• 执行日志：查看详细的操作日志和错误信息
• GitHub 文档：https://docs.github.com/cn
• Git 文档：https://git-scm.com/doc

💡 提示：遇到问题时，先查看执行日志，里面有详细的错误信息！
        """
        
        help_display = scrolledtext.ScrolledText(frame, width=90, height=40, 
                                                 font=('Consolas', 9), wrap=tk.WORD)
        help_display.pack(padx=20, pady=20, fill='both', expand=True)
        help_display.insert('1.0', help_text)
        help_display.config(state='disabled')
    
    def setup_ssh_guide(self):
        """SSH 配置向导"""
        guide = tk.Toplevel(self.root)
        guide.title("SSH 配置向导")
        guide.geometry("600x500")
        
        ttk.Label(guide, text="SSH 配置向导", font=('Arial', 14, 'bold')).pack(pady=20)
        
        steps = scrolledtext.ScrolledText(guide, width=70, height=20, wrap=tk.WORD)
        steps.pack(padx=20, pady=10)
        
        user_email = self.git_email.get() or "your_email@example.com"
        
        steps_text = f"""
═══════════════════════════════════════════════════════

              SSH 密钥配置完整指南

═══════════════════════════════════════════════════════

第一步：生成 SSH 密钥
─────────────────────────────────────────────────

打开命令行工具（CMD、PowerShell 或 Terminal）

执行以下命令：

ssh-keygen -t rsa -b 4096 -C "{user_email}"

遇到提示时：
  • "Enter file in which to save the key"
    → 直接按回车（使用默认位置）
  
  • "Enter passphrase (empty for no passphrase)"
    → 直接按回车（不设置密码）
  
  • "Enter same passphrase again"
    → 再次按回车

✅ 看到类似 "Your public key has been saved" 即成功


第二步：获取公钥内容
─────────────────────────────────────────────────

Windows 用户执行：
  type %USERPROFILE%\\.ssh\\id_rsa.pub

Mac/Linux 用户执行：
  cat ~/.ssh/id_rsa.pub

📋 复制显示的全部内容
   （从 ssh-rsa 开始到邮箱结束）


第三步：添加公钥到 GitHub
─────────────────────────────────────────────────

1. 点击下方"打开 GitHub SSH 设置"按钮
   （或访问：https://github.com/settings/ssh/new）

2. 在打开的页面中：
   • Title：填写备注（如：My-Laptop）
   • Key：粘贴刚才复制的公钥
   • 点击"Add SSH key"按钮
   • 输入 GitHub 密码确认


第四步：测试连接
─────────────────────────────────────────────────

点击下方"测试 SSH"按钮

或在命令行执行：
  ssh -T git@github.com

看到 "successfully authenticated" 即成功！


═══════════════════════════════════════════════════════

💡 提示：
  • 点击"自动配置 SSH"可自动完成大部分步骤
  • 公钥会自动复制到剪贴板
  • 只需要手动在 GitHub 上粘贴即可

═══════════════════════════════════════════════════════
        """
        
        steps.insert('1.0', steps_text)
        steps.config(state='disabled')
        
        btn_frame = ttk.Frame(guide)
        btn_frame.pack(pady=20)
        
        ttk.Button(btn_frame, text="🔧 自动配置 SSH", 
                  command=lambda: self.auto_setup_ssh(guide), width=20).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="🌐 打开 GitHub SSH 设置", 
                  command=lambda: self.open_ssh_settings(), width=25).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="✓ 测试 SSH", 
                  command=self.test_ssh, width=15).pack(side='left', padx=5)
    
    def auto_setup_ssh(self, parent=None):
        """自动配置 SSH"""
        self.log("=== 自动配置 SSH ===")
        
        home = Path.home()
        ssh_dir = home / '.ssh'
        key_file = ssh_dir / 'id_rsa'
        
        if not key_file.exists():
            self.log("❌ SSH 密钥不存在")
            result = messagebox.askyesno(
                "生成密钥",
                "未找到 SSH 密钥\n\n是否自动生成？\n"
                "（将使用默认设置，无密码保护）"
            )
            if result:
                email = self.git_email.get()
                if not email:
                    email = simpledialog.askstring(
                        "输入邮箱",
                        "请输入你的邮箱地址：",
                        initialvalue="your_email@example.com"
                    )
                    if not email:
                        return
                
                self.log(f"正在生成密钥（邮箱：{email}）...")
                success, _, _ = self.run_command(
                    f'ssh-keygen -t rsa -b 4096 -C "{email}" -f "%USERPROFILE%\\.ssh\\id_rsa" -N ""',
                    show_output=False
                )
                if success:
                    self.log("✅ 密钥生成成功")
                else:
                    self.log("❌ 密钥生成失败，请手动执行命令")
                    messagebox.showerror("失败", "自动生成失败\n\n请按照向导手动执行命令")
                    return
            else:
                return
        else:
            self.log("✅ SSH 密钥已存在")
        
        self.log("正在添加 GitHub 主机密钥...")
        if self.fix_ssh_known_hosts():
            self.log("✅ 主机密钥配置完成")
        
        self.log("正在测试连接...")
        success, output, error = self.run_command(
            "ssh -T git@github.com -o StrictHostKeyChecking=no",
            check_error=False,
            show_output=False
        )
        
        if "successfully authenticated" in output or "successfully authenticated" in error:
            self.log("✅ SSH 配置成功！")
            messagebox.showinfo("成功", "SSH 配置成功！\n\n可以使用 SSH 方式上传代码了")
        else:
            self.log("⚠️ 需要添加公钥到 GitHub")
            
            pub_key_file = ssh_dir / 'id_rsa.pub'
            if pub_key_file.exists():
                with open(pub_key_file, 'r') as f:
                    pub_key = f.read().strip()
                
                try:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(pub_key)
                    self.log("✅ 公钥已复制到剪贴板")
                except:
                    pass
                
                messagebox.showinfo(
                    "添加公钥",
                    "公钥已复制到剪贴板！\n\n"
                    "接下来的步骤：\n"
                    "1. 点击'确定'后会自动打开 GitHub\n"
                    "2. Title 随便填（如：My-Computer）\n"
                    "3. Key 粘贴公钥（Ctrl+V）\n"
                    "4. 点击 Add SSH key\n"
                    "5. 返回工具点击'测试 SSH'验证\n\n"
                    "💡 提示：公钥已在剪贴板中，直接粘贴即可"
                )
                
                self.open_ssh_settings()
    
    def open_ssh_settings(self):
        """打开 GitHub SSH 设置页面"""
        import webbrowser
        webbrowser.open("https://github.com/settings/ssh/new")
    
    def open_token_page(self):
        """打开 Token 生成页面"""
        import webbrowser
        webbrowser.open("https://github.com/settings/tokens/new")
    
    def test_token(self):
        """测试 Token"""
        token = self.github_token.get().strip()
        if not token:
            messagebox.showerror("错误", "请先填写 Token")
            return
        
        self.log("=== 测试 Token ===")
        
        def task():
            self.progress.start()
            try:
                import urllib.request
                import json as json_module
                
                req = urllib.request.Request("https://api.github.com/user")
                req.add_header("Authorization", f"token {token}")
                
                response = urllib.request.urlopen(req, timeout=10)
                data = json_module.loads(response.read())
                
                username = data.get('login', '未知')
                self.log(f"✅ Token 有效！用户：{username}")
                
                scopes = response.headers.get('X-OAuth-Scopes', '')
                if 'repo' in scopes:
                    self.log("✅ 拥有 repo 权限")
                    messagebox.showinfo("成功", f"Token 验证成功！\n用户：{username}")
                else:
                    self.log("⚠️ 缺少 repo 权限")
                    messagebox.showwarning("警告", "Token 有效但缺少 repo 权限\n请重新生成")
                
            except Exception as e:
                self.log(f"❌ Token 无效或已过期")
                messagebox.showerror("失败", "Token 无效或已过期")
            finally:
                self.progress.stop()
        
        threading.Thread(target=task, daemon=True).start()
    
    def browse_folder(self):
        """浏览文件夹"""
        folder = filedialog.askdirectory()
        if folder:
            self.repo_path.set(folder)
    
    def log(self, message):
        """添加日志"""
        try:
            self.log_text.config(state='normal')
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)
            self.log_text.config(state='disabled')
            self.root.update()
        except:
            print(message)
    
    def run_command(self, command, cwd=None, check_error=True, show_output=True):
        """执行命令"""
        try:
            result = subprocess.run(
                command,
                cwd=cwd or self.repo_path.get() or os.getcwd(),
                capture_output=True,
                text=True,
                shell=True,
                encoding='utf-8',
                errors='ignore',
                timeout=300  # 5分钟超时
            )
            
            if show_output:
                if result.stdout and result.stdout.strip():
                    self.log(result.stdout.strip())
                if result.stderr and result.stderr.strip():
                    if result.returncode != 0:
                        error_msg = result.stderr.strip()
                        if "Host key verification failed" in error_msg:
                            self.log("⚠️ 错误：SSH 主机密钥验证失败（首次连接需要确认）")
                        elif "Permission denied" in error_msg and "publickey" in error_msg:
                            self.log("⚠️ 错误：SSH 密钥认证失败（密钥未添加到 GitHub）")
                        elif "403" in error_msg:
                            self.log("⚠️ 错误：访问被拒绝（Token 无效或权限不足）")
                        elif "Connection was reset" in error_msg or "Connection refused" in error_msg:
                            self.log("⚠️ 错误：网络连接失败")
                        elif "timeout" in error_msg.lower():
                            self.log("⚠️ 错误：网络超时")
                        else:
                            self.log(f"⚠️ {error_msg}")
                    else:
                        self.log(result.stderr.strip())
            
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            self.log("❌ 命令执行超时（超过5分钟）")
            return False, "", "Timeout"
        except Exception as e:
            self.log(f"❌ 执行错误：{str(e)}")
            return False, "", str(e)
    
    def check_git_config(self):
        """检查 Git 配置"""
        if not self.check_git_installed():
            return
        
        self.log("=== 检查 Git 配置 ===")
        
        success, username, _ = self.run_command("git config --global user.name", check_error=False, show_output=False)
        success2, email, _ = self.run_command("git config --global user.email", check_error=False, show_output=False)
        
        if username.strip():
            self.git_username.set(username.strip())
            self.log(f"✅ 用户名：{username.strip()}")
        else:
            self.log("⚠️ 未配置用户名")
            
        if email.strip():
            self.git_email.set(email.strip())
            self.log(f"✅ 邮箱：{email.strip()}")
        else:
            self.log("⚠️ 未配置邮箱")
        
        success, config, _ = self.run_command("git config --list", check_error=False, show_output=False)
        if success:
            self.config_display.config(state='normal')
            self.config_display.delete(1.0, tk.END)
            self.config_display.insert(tk.END, config)
            self.config_display.config(state='disabled')
    
    def save_git_config(self):
        """保存 Git 配置"""
        username = self.git_username.get().strip()
        email = self.git_email.get().strip()
        
        if not username or not email:
            messagebox.showerror("错误", "请填写用户名和邮箱")
            return
        
        self.log("=== 保存 Git 配置 ===")
        self.run_command(f'git config --global user.name "{username}"', show_output=False)
        self.run_command(f'git config --global user.email "{email}"', show_output=False)
        
        self.log("✅ 配置保存成功")
        messagebox.showinfo("成功", "配置已保存")
        self.check_git_config()
    
    def test_ssh(self):
        """测试 SSH"""
        self.log("=== 测试 SSH 连接 ===")
        
        self.fix_ssh_known_hosts()
        
        success, output, error = self.run_command(
            "ssh -T git@github.com -o StrictHostKeyChecking=no",
            check_error=False,
            show_output=False
        )
        
        if "successfully authenticated" in output or "successfully authenticated" in error:
            self.log("✅ SSH 配置正确，可以使用！")
            messagebox.showinfo("成功", "SSH 配置正确\n可以使用 SSH 方式上传代码")
        elif "Permission denied" in error:
            self.log("❌ SSH 密钥未添加到 GitHub")
            result = messagebox.askyesno(
                "SSH 未配置",
                "SSH 密钥未添加到 GitHub\n\n是否打开配置向导？"
            )
            if result:
                self.setup_ssh_guide()
        else:
            self.log("❌ SSH 连接失败")
            messagebox.showerror("失败", "SSH 连接失败\n请检查网络或查看使用帮助")
    
    def check_remote_exists(self, remote_name="origin"):
        """检查远程仓库是否存在"""
        success, output, _ = self.run_command("git remote", check_error=False, show_output=False)
        if success:
            return remote_name in output.split()
        return False
    
    def detect_remote_branch(self):
        """检测远程分支"""
        if not self.check_remote_exists():
            messagebox.showwarning("提示", "请先初始化仓库")
            return
        
        self.log("=== 检测远程分支 ===")
        success, output, _ = self.run_command("git ls-remote --heads origin", check_error=False, show_output=False)
        
        if success and output.strip():
            branches = []
            for line in output.split('\n'):
                if 'refs/heads/' in line:
                    branch = line.split('refs/heads/')[-1].strip()
                    if branch:
                        branches.append(branch)
            
            if branches:
                self.log(f"远程分支：{', '.join(branches)}")
                self.branch.set(branches[0])
                messagebox.showinfo("检测完成", f"远程分支：{', '.join(branches)}\n已设置为：{branches[0]}")
            else:
                messagebox.showinfo("提示", "远程仓库为空\n首次推送将创建分支")
        else:
            messagebox.showinfo("提示", "远程仓库为空\n首次推送将创建分支")
    
    def check_status(self):
        """检查仓库状态"""
        def task():
            self.progress.start()
            repo_path = self.repo_path.get()
            
            if not repo_path or not os.path.exists(repo_path):
                messagebox.showerror("错误", "路径无效")
                self.progress.stop()
                return
            
            self.log("=== 仓库状态 ===")
            
            if not os.path.exists(os.path.join(repo_path, '.git')):
                self.log("❌ 不是 Git 仓库")
                self.progress.stop()
                return
            
            success, branch, _ = self.run_command("git branch --show-current", check_error=False, show_output=False)
            if branch.strip():
                self.log(f"📌 当前分支：{branch.strip()}")
                self.branch.set(branch.strip())
            
            success, remote, _ = self.run_command("git remote -v", check_error=False, show_output=False)
            if remote.strip():
                self.log(f"🔗 远程仓库：\n{remote.strip()}")
            
            self.run_command("git status")
            
            self.log("=== 检查完成 ===")
            self.progress.stop()
        
        threading.Thread(target=task, daemon=True).start()
    
    def init_repo(self):
        """初始化仓库"""
        def task():
            self.progress.start()
            repo_path = self.repo_path.get()
            git_url = self.get_correct_url()
            branch = self.branch.get()
            
            if not repo_path or not git_url:
                messagebox.showerror("错误", "请填写仓库路径和地址")
                self.progress.stop()
                return
            
            if not os.path.exists(repo_path):
                if messagebox.askyesno("创建目录", f"目录不存在，是否创建？\n{repo_path}"):
                    try:
                        os.makedirs(repo_path, exist_ok=True)
                    except Exception as e:
                        messagebox.showerror("错误", f"创建目录失败：{e}")
                        self.progress.stop()
                        return
                else:
                    self.progress.stop()
                    return
            
            self.log("=== 初始化仓库 ===")
            
            if not os.path.exists(os.path.join(repo_path, '.git')):
                self.run_command("git init")
            else:
                self.log("✅ 仓库已存在")
            
            if self.check_remote_exists("origin"):
                self.run_command("git remote remove origin", show_output=False)
            
            self.run_command(f"git remote add origin {git_url}")
            self.run_command(f"git branch -M {branch}", check_error=False)
            
            self.log("=== ✅ 初始化完成 ===")
            self.progress.stop()
            messagebox.showinfo("成功", "仓库初始化完成")
        
        threading.Thread(target=task, daemon=True).start()
    
    def commit_only(self):
        """仅提交"""
        def task():
            self.progress.start()
            commit_message = self.commit_msg.get("1.0", tk.END).strip()
            file_pattern = self.file_pattern.get()
            
            if not commit_message:
                messagebox.showerror("错误", "请填写提交信息")
                self.progress.stop()
                return
            
            # 清理提交信息
            commit_message = self.sanitize_commit_message(commit_message)
            
            self.log("=== 提交到本地 ===")
            
            self.run_command(f"git add {file_pattern}")
            
            success, status, _ = self.run_command("git status --short", check_error=False, show_output=False)
            if not status.strip():
                self.log("ℹ️ 没有文件变更")
                self.progress.stop()
                messagebox.showinfo("提示", "没有文件需要提交")
                return
            
            self.run_command(f'git commit -m "{commit_message}"')
            self.log("=== ✅ 提交完成 ===")
            self.progress.stop()
            messagebox.showinfo("成功", "已提交到本地")
        
        threading.Thread(target=task, daemon=True).start()
    
    def push_only(self):
        """仅推送"""
        def task():
            self.progress.start()
            branch = self.branch.get()
            git_url = self.get_correct_url()
            
            self.log("=== 推送到远程 ===")
            
            if self.connection_type.get() == "ssh":
                self.fix_ssh_known_hosts()
                
                success, _, stderr = self.run_command(
                    f"git push -u origin {branch}",
                    check_error=False
                )
                
                if not success:
                    if "Host key verification failed" in stderr:
                        self.log("🔧 检测到 SSH 首次连接问题，正在自动修复...")
                        if self.fix_ssh_known_hosts():
                            self.log("✅ 修复完成，重新推送...")
                            success, _, stderr = self.run_command(f"git push -u origin {branch}")
                    
                    elif "rejected" in stderr or "non-fast-forward" in stderr:
                        self.log("⚠️ 远程仓库有新的提交")
                        result = messagebox.askyesnocancel(
                            "远程仓库冲突",
                            "远程仓库有新的提交，本地落后于远程\n\n"
                            "请选择处理方式：\n\n"
                            "【是】- 拉取远程更改并合并（推荐）\n"
                            "      会保留远程和本地的所有提交\n\n"
                            "【否】- 强制推送（危险！会覆盖远程）\n"
                            "      会丢失远程的新提交\n\n"
                            "【取消】- 不执行任何操作"
                        )
                        
                        if result is True:
                            self.log("正在拉取远程更改...")
                            pull_success, _, pull_error = self.run_command(
                                f"git pull origin {branch} --rebase",
                                check_error=False
                            )
                            
                            if pull_success or "CONFLICT" not in pull_error:
                                self.log("✅ 拉取成功，重新推送...")
                                success, _, _ = self.run_command(f"git push origin {branch}")
                                if success:
                                    self.log("=== ✅ 推送成功！===")
                                    messagebox.showinfo("成功", "代码已成功推送到 GitHub！")
                                else:
                                    messagebox.showerror("失败", "推送仍然失败，请查看日志")
                            else:
                                self.log("❌ 拉取时发生冲突")
                                messagebox.showerror(
                                    "合并冲突",
                                    "拉取时发生冲突！\n\n"
                                    "需要手动解决冲突：\n"
                                    "1. 打开命令行进入仓库目录\n"
                                    "2. 编辑冲突文件\n"
                                    "3. 执行: git add .\n"
                                    "4. 执行: git rebase --continue\n"
                                    "5. 执行: git push origin " + branch
                                )
                        elif result is False:
                            confirm = messagebox.askyesno(
                                "⚠️ 危险操作确认",
                                "强制推送会覆盖远程仓库的所有新提交！\n\n"
                                "这意味着：\n"
                                "• 远程的新文件会被删除\n"
                                "• 远程的新修改会丢失\n"
                                "• 无法恢复\n\n"
                                "确定要强制推送吗？",
                                icon='warning'
                            )
                            if confirm:
                                self.log("⚠️ 执行强制推送...")
                                success, _, _ = self.run_command(f"git push -f origin {branch}")
                                if success:
                                    self.log("=== ✅ 强制推送成功 ===")
                                    messagebox.showwarning("成功", "强制推送完成\n远程旧提交已被覆盖")
                                else:
                                    messagebox.showerror("失败", "强制推送失败")
                        
                        self.progress.stop()
                        return
            else:
                token = self.github_token.get().strip()
                if token and "github.com" in git_url:
                    auth_url = git_url.replace("https://", f"https://{token}@")
                    success, _, stderr = self.run_command(f"git push -u {auth_url} {branch}")
                else:
                    success, _, stderr = self.run_command(f"git push -u origin {branch}")
                
                if not success and ("rejected" in stderr or "non-fast-forward" in stderr):
                    result = messagebox.askyesnocancel(
                        "远程仓库冲突",
                        "远程仓库有新的提交\n\n"
                        "【是】- 拉取并合并\n"
                        "【否】- 强制推送（危险）\n"
                        "【取消】- 取消操作"
                    )
                    
                    if result is True:
                        self.run_command(f"git pull origin {branch} --rebase")
                        if token and "github.com" in git_url:
                            auth_url = git_url.replace("https://", f"https://{token}@")
                            success, _, _ = self.run_command(f"git push {auth_url} {branch}")
                        else:
                            success, _, _ = self.run_command(f"git push origin {branch}")
                    elif result is False:
                        if messagebox.askyesno("确认", "确定强制推送？", icon='warning'):
                            if token and "github.com" in git_url:
                                auth_url = git_url.replace("https://", f"https://{token}@")
                                success, _, _ = self.run_command(f"git push -f {auth_url} {branch}")
                            else:
                                success, _, _ = self.run_command(f"git push -f origin {branch}")
                    
                    self.progress.stop()
                    return
            
            if success:
                self.log("=== ✅ 推送成功！===")
                messagebox.showinfo("成功", "代码已成功推送到 GitHub！")
            else:
                if "Permission denied" in stderr and "publickey" in stderr:
                    result = messagebox.askyesno(
                        "SSH 认证失败",
                        "SSH 密钥未配置或未添加到 GitHub\n\n是否打开配置向导？"
                    )
                    if result:
                        self.setup_ssh_guide()
                elif "403" in stderr:
                    messagebox.showerror("认证失败", "Token 无效或权限不足\n请重新生成 Token")
                else:
                    messagebox.showerror("推送失败", "推送失败，请查看日志")
            
            self.progress.stop()
        
        threading.Thread(target=task, daemon=True).start()
    
    def full_workflow(self):
        """完整工作流程"""
        def task():
            self.progress.start()
            repo_path = self.repo_path.get()
            git_url = self.get_correct_url()
            commit_message = self.commit_msg.get("1.0", tk.END).strip()
            file_pattern = self.file_pattern.get()
            branch = self.branch.get()
            
            if not repo_path or not git_url or not commit_message:
                messagebox.showerror("错误", "请填写所有必要信息")
                self.progress.stop()
                return
            
            # 清理提交信息
            commit_message = self.sanitize_commit_message(commit_message)
            
            # 检查磁盘空间
            if not self.check_disk_space(repo_path):
                if not messagebox.askyesno("警告", "磁盘空间不足\n是否继续？"):
                    self.progress.stop()
                    return
            
            if self.connection_type.get() == "ssh":
                is_configured, msg = self.check_ssh_configured()
                if not is_configured:
                    result = messagebox.askyesno(
                        "SSH 未配置",
                        f"{msg}\n\n是否打开配置向导？\n\n"
                        "（或者可以切换到 HTTPS 方式）"
                    )
                    if result:
                        self.setup_ssh_guide()
                        self.progress.stop()
                        return
                    else:
                        self.progress.stop()
                        return
            elif not self.github_token.get().strip():
                result = messagebox.askyesno("提示", "HTTPS 方式需要 Token\n\n是否继续？（可能失败）")
                if not result:
                    self.progress.stop()
                    return
            
            self.log("=== 🚀 开始一键上传 ===\n")
            
            if not os.path.exists(repo_path):
                try:
                    os.makedirs(repo_path, exist_ok=True)
                except Exception as e:
                    messagebox.showerror("错误", f"创建目录失败：{e}")
                    self.progress.stop()
                    return
            
            self.log("[1/5] 初始化仓库")
            if not os.path.exists(os.path.join(repo_path, '.git')):
                self.run_command("git init")
            else:
                self.log("✅ 仓库已存在")
            
            self.log("\n[2/5] 设置远程仓库")
            if self.check_remote_exists("origin"):
                self.run_command("git remote remove origin", show_output=False)
            self.run_command(f"git remote add origin {git_url}")
            self.run_command(f"git branch -M {branch}", check_error=False)
            
            self.log("\n[3/5] 添加文件")
            self.run_command(f"git add {file_pattern}")
            
            success, status, _ = self.run_command("git status --short", check_error=False, show_output=False)
            if not status.strip():
                self.log("创建 README.md")
                try:
                    with open(os.path.join(repo_path, "README.md"), "w", encoding="utf-8") as f:
                        f.write(f"# {os.path.basename(repo_path)}\n\n{commit_message}\n")
                    self.run_command("git add README.md")
                except Exception as e:
                    self.log(f"⚠️ 创建 README 失败：{e}")
            
            self.log("\n[4/5] 提交更改")
            self.run_command(f'git commit -m "{commit_message}"')
            
            self.log("\n[5/5] 推送到 GitHub")
            
            if self.connection_type.get() == "ssh":
                self.fix_ssh_known_hosts()
                success, _, stderr = self.run_command(f"git push -u origin {branch}", check_error=False)
                
                if not success:
                    if "Host key verification failed" in stderr:
                        self.log("🔧 自动修复 SSH 连接问题...")
                        self.fix_ssh_known_hosts()
                        success, _, stderr = self.run_command(f"git push -u origin {branch}", check_error=False)
                    
                    if not success and ("rejected" in stderr or "non-fast-forward" in stderr):
                        self.log("⚠️ 检测到远程仓库有新的提交")
                        result = messagebox.askyesnocancel(
                            "远程仓库冲突",
                            "远程仓库有新的提交（可能是在网页上创建的 README 等）\n\n"
                            "请选择处理方式：\n\n"
                            "【是】- 拉取远程更改并合并（推荐）\n"
                            "      会保留远程和本地的所有提交\n\n"
                            "【否】- 强制推送（会覆盖远程新提交）\n\n"
                            "【取消】- 停止操作",
                            icon='warning'
                        )
                        
                        if result is True:
                            self.log("正在拉取远程更改...")
                            pull_success, _, pull_error = self.run_command(
                                f"git pull origin {branch} --rebase",
                                check_error=False
                            )
                            
                            if pull_success or "CONFLICT" not in pull_error:
                                self.log("✅ 拉取成功，重新推送...")
                                success, _, _ = self.run_command(f"git push origin {branch}")
                            else:
                                self.log("❌ 合并冲突，需要手动解决")
                                messagebox.showerror(
                                    "合并冲突",
                                    "拉取时发生冲突，需要手动解决\n\n"
                                    "建议操作：\n"
                                    "1. 打开命令行进入仓库目录\n"
                                    "2. 执行: git status 查看冲突文件\n"
                                    "3. 编辑冲突文件解决冲突\n"
                                    "4. 执行: git add .\n"
                                    "5. 执行: git rebase --continue\n"
                                    "6. 执行: git push origin " + branch
                                )
                                self.progress.stop()
                                return
                        
                        elif result is False:
                            if messagebox.askyesno(
                                "⚠️ 危险操作",
                                "强制推送会覆盖远程的所有新提交！\n确定吗？",
                                icon='warning'
                            ):
                                self.log("⚠️ 执行强制推送...")
                                success, _, _ = self.run_command(f"git push -f origin {branch}")
                        else:
                            self.log("❌ 用户取消操作")
                            self.progress.stop()
                            return
            else:
                token = self.github_token.get().strip()
                if token and "github.com" in git_url:
                    auth_url = git_url.replace("https://", f"https://{token}@")
                    success, _, stderr = self.run_command(f"git push -u {auth_url} {branch}", check_error=False)
                else:
                    success, _, stderr = self.run_command(f"git push -u origin {branch}", check_error=False)
                
                if not success and ("rejected" in stderr or "non-fast-forward" in stderr):
                    result = messagebox.askyesnocancel(
                        "远程仓库冲突",
                        "远程仓库有新的提交\n\n"
                        "【是】- 拉取并合并\n"
                        "【否】- 强制推送（危险）\n"
                        "【取消】- 取消操作"
                    )
                    
                    if result is True:
                        self.run_command(f"git pull origin {branch} --rebase")
                        if token and "github.com" in git_url:
                            auth_url = git_url.replace("https://", f"https://{token}@")
                            success, _, _ = self.run_command(f"git push {auth_url} {branch}")
                        else:
                            success, _, _ = self.run_command(f"git push origin {branch}")
                    elif result is False:
                        if messagebox.askyesno("确认", "确定强制推送？", icon='warning'):
                            if token and "github.com" in git_url:
                                auth_url = git_url.replace("https://", f"https://{token}@")
                                success, _, _ = self.run_command(f"git push -f {auth_url} {branch}")
                            else:
                                success, _, _ = self.run_command(f"git push -f origin {branch}")
                    else:
                        self.progress.stop()
                        return
            
            if success:
                self.log("\n=== ✅ 上传成功！===")
                self.log(f"🎉 代码已推送到：{git_url}")
                messagebox.showinfo("成功", f"代码已成功上传到 GitHub！\n\n仓库：{git_url}")
            else:
                if "Permission denied" in stderr and "publickey" in stderr:
                    result = messagebox.askyesno(
                        "SSH 认证失败",
                        "SSH 密钥未配置\n\n是否打开配置向导？"
                    )
                    if result:
                        self.setup_ssh_guide()
                elif "403" in stderr:
                    messagebox.showerror("Token 失败", "Token 无效或权限不足\n\n请点击'测试 Token'验证")
                else:
                    messagebox.showerror("上传失败", "上传失败，请查看日志了解详情")
            
            self.progress.stop()
        
        threading.Thread(target=task, daemon=True).start()
    
    def save_config(self):
        """保存配置"""
        try:
            config = {
                "repo_path": self.repo_path.get(),
                "git_url": self.git_url.get(),
                "branch": self.branch.get(),
                "file_pattern": self.file_pattern.get(),
                "connection_type": self.connection_type.get(),
                "github_token": self.github_token.get()
            }
            
            with open(self.config_file, "w", encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.log("✅ 配置已保存")
            messagebox.showinfo("成功", "配置已保存")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败：{e}")
    
    def load_config(self):
        """加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r", encoding='utf-8') as f:
                    config = json.load(f)
                
                self.repo_path.set(config.get("repo_path", ""))
                self.git_url.set(config.get("git_url", ""))
                self.branch.set(config.get("branch", "main"))
                self.file_pattern.set(config.get("file_pattern", "."))
                self.connection_type.set(config.get("connection_type", "ssh"))
                self.github_token.set(config.get("github_token", ""))
                
                self.update_url_example()
                self.check_url_format()
                self.log("✅ 已加载配置")
        except json.JSONDecodeError:
            self.log("⚠️ 配置文件格式错误，已忽略")
            # 删除损坏的配置文件
            try:
                os.remove(self.config_file)
            except:
                pass
        except Exception as e:
            self.log(f"⚠️ 加载配置失败：{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = GitUploader(root)
    root.mainloop()