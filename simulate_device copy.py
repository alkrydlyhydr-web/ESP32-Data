import tkinter as tk

root = tk.Tk()
root.geometry("400x120")

entry = tk.Entry(root, font=("Tahoma", 16), justify="right")
entry.pack(fill="x", padx=20, pady=20)

root.mainloop()