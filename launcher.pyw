"""
啟動器：在子程序跑 sf_tracker.py，攔截視窗關閉事件彈確認框
.pyw 副檔名不會開 CMD 視窗，用 tkinter 當 GUI 殼
"""
import subprocess
import sys
import os
import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sf_tracker.py")


class TrackerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SF Express Tracker")
        self.root.geometry("750x420")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 輸出區
        self.text = scrolledtext.ScrolledText(
            self.root, wrap=tk.WORD, bg="#1e1e1e", fg="#cccccc",
            font=("Consolas", 10), insertbackground="#cccccc",
        )
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.text.config(state=tk.DISABLED)

        # 底部按鈕
        frame = tk.Frame(self.root)
        frame.pack(fill=tk.X, padx=5, pady=5)
        self.stop_btn = tk.Button(
            frame, text="Stop Tracking", command=self.on_close,
            bg="#cc3333", fg="white", font=("Arial", 10, "bold"),
        )
        self.stop_btn.pack(side=tk.RIGHT)

        self.process = None
        self.running = True

        # 啟動追蹤程式
        threading.Thread(target=self.run_tracker, daemon=True).start()

    def append_text(self, text):
        self.text.config(state=tk.NORMAL)
        self.text.insert(tk.END, text)
        self.text.see(tk.END)
        self.text.config(state=tk.DISABLED)

    def run_tracker(self):
        """在子程序執行 sf_tracker.py"""
        # 找 python
        py = sys.executable

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        try:
            self.process = subprocess.Popen(
                [py, "-X", "utf8", SCRIPT],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(SCRIPT),
                env=env,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            for line in self.process.stdout:
                if not self.running:
                    break
                self.root.after(0, self.append_text, line)

            self.process.wait()
            self.root.after(0, self.append_text, "\n--- Program ended ---\n")

        except Exception as e:
            self.root.after(0, self.append_text, f"\nError: {e}\n")

    def on_close(self):
        """關閉確認"""
        if self.process and self.process.poll() is None:
            answer = messagebox.askyesno(
                "Confirm Exit",
                "Tracker is still running.\nAre you sure you want to stop?",
            )
            if not answer:
                return

        self.running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = TrackerApp()
    app.run()
