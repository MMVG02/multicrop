import tkinter as tk
from tkinter import filedialog, messagebox, Listbox
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid
import math

# Constants
RECT_TAG_PREFIX = "crop_rect_"
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
MIN_CROP_SIZE = 10

class MultiCropApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Multi Image Cropper")
        self.geometry("1000x700")
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        # State variables
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.tk_image = None
        self.canvas_image_id = None
        self.crops = {}
        self.crop_order = []
        self.selected_crop_id = None
        self.dragging = False
        self.drag_start_index = None

        # Drawing/Editing State
        self.start_x = None
        self.start_y = None
        self.current_rect_id = None
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.move_offset_x = 0
        self.move_offset_y = 0

        # Zoom/Pan State
        self.zoom_factor = 1.0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_panning = False
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0

        # UI Layout
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Image Frame
        self.image_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self.image_frame, bg="gray90", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Control Frame
        self.control_frame = ctk.CTkFrame(self, width=250)
        self.control_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False)
        self.control_frame.grid_rowconfigure(3, weight=1)

        # Widgets
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image", command=self.select_image)
        self.btn_select_image.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        
        self.btn_save_crops = ctk.CTkButton(self.control_frame, text="Save All Crops", command=self.save_crops, state=tk.DISABLED)
        self.btn_save_crops.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List:")
        self.lbl_crop_list.grid(row=2, column=0, padx=10, pady=(10, 0), sticky="w")
        
        self.crop_listbox = Listbox(self.control_frame, bg='white', fg='black', selectbackground='#CDEAFE',
                                  selectforeground='black', highlightthickness=1, highlightbackground="#CCCCCC",
                                  highlightcolor="#89C4F4", borderwidth=0, exportselection=False, selectmode=tk.EXTENDED)
        self.crop_listbox.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
        
        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete Selected", command=self.delete_selected_crop,
                                           state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crop.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1))
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1))
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press)
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.update_cursor)
        self.bind("<Delete>", self.delete_selected_crop_event)
        self.bind("<Configure>", self.on_window_resize)
        
        self.crop_listbox.bind('<<ListboxSelect>>', self.on_listbox_select)
        self.crop_listbox.bind('<ButtonPress-1>', self.on_listbox_press)
        self.crop_listbox.bind('<B1-Motion>', self.on_listbox_drag)
        self.crop_listbox.bind('<ButtonRelease-1>', self.on_listbox_release)
        self.crop_listbox.bind('<Double-Button-1>', self.on_listbox_double_click)

    # --------------------- Improved Features Implementation ---------------------
    def on_double_click(self, event):
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        clicked_crop_id = self.get_clicked_crop_id(canvas_x, canvas_y)
        if clicked_crop_id:
            self.select_crop(clicked_crop_id, from_listbox=False)

    def on_listbox_press(self, event):
        self.drag_start_index = self.crop_listbox.nearest(event.y)
        self.dragging = self.drag_start_index >= 0

    def on_listbox_drag(self, event):
        if not self.dragging:
            return
        current_index = self.crop_listbox.nearest(event.y)
        if current_index != self.drag_start_index and current_index >= 0:
            item = self.crop_listbox.get(self.drag_start_index)
            crop_id = self.crop_order.pop(self.drag_start_index)
            self.crop_order.insert(current_index, crop_id)
            self.crop_listbox.delete(self.drag_start_index)
            self.crop_listbox.insert(current_index, item)
            self.drag_start_index = current_index

    def on_listbox_release(self, event):
        self.dragging = False

    def on_listbox_double_click(self, event):
        index = self.crop_listbox.nearest(event.y)
        if index < 0 or index >= len(self.crop_order):
            return
        crop_id = self.crop_order[index]
        self.create_rename_entry(index, crop_id)

    def create_rename_entry(self, index, crop_id):
        entry = ctk.CTkEntry(self.crop_listbox)
        entry.insert(0, self.crops[crop_id]['name'])
        entry.bind('<Return>', lambda e, i=index, c=crop_id: self.finalize_rename(e, i, c))
        entry.bind('<FocusOut>', lambda e, i=index, c=crop_id: self.finalize_rename(e, i, c))
        bbox = self.crop_listbox.bbox(index)
        if bbox:
            entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
            entry.focus_set()

    def finalize_rename(self, event, index, crop_id):
        new_name = event.widget.get()
        self.crops[crop_id]['name'] = new_name
        self.crop_listbox.delete(index)
        self.crop_listbox.insert(index, new_name)
        event.widget.destroy()

    def delete_selected_crop(self, event=None):
        selected_indices = self.crop_listbox.curselection()
        if not selected_indices:
            return
        
        # Delete in reverse order to maintain indices
        for index in reversed(sorted(selected_indices)):
            if index >= len(self.crop_order):
                continue
            crop_id = self.crop_order.pop(index)
            if crop_id in self.crops:
                self.canvas.delete(self.crops[crop_id]['rect_id'])
                del self.crops[crop_id]
        
        self.update_listbox()
        self.selected_crop_id = None
        self.btn_delete_crop.configure(state=tk.DISABLED)
        if not self.crops:
            self.btn_save_crops.configure(state=tk.DISABLED)

    def update_listbox(self):
        self.crop_listbox.delete(0, tk.END)
        for crop_id in self.crop_order:
            self.crop_listbox.insert(tk.END, self.crops[crop_id]['name'])

    def get_next_crop_number(self):
        base_name = os.path.splitext(os.path.basename(self.image_path))[0] if self.image_path else "Image"
        used_numbers = []
        for crop_id in self.crops:
            name = self.crops[crop_id]['name']
            if name.startswith(f"{base_name}_Crop_"):
                try:
                    used_numbers.append(int(name.split('_')[-1]))
                except ValueError:
                    pass
        next_num = 1
        while next_num in used_numbers:
            next_num += 1
        return next_num

    # --------------------- Core Application Logic (Maintained with improvements) ---------------------
    def select_image(self):
        path = filedialog.askopenfilename(filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff")])
        if not path:
            return

        try:
            self.image_path = path
            self.original_image = Image.open(self.image_path)
            self.clear_crops_and_list()
            self.display_image_on_canvas()
            self.btn_save_crops.configure(state=tk.DISABLED)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open image:\n{e}")
            self.reset_image_state()

    def display_image_on_canvas(self):
        if not self.original_image:
            return

        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        img_width, img_height = self.original_image.size

        zoom_h = canvas_width / img_width
        zoom_v = canvas_height / img_height
        self.zoom_factor = min(zoom_h, zoom_v) * 0.98

        display_w = int(img_width * self.zoom_factor)
        display_h = int(img_height * self.zoom_factor)
        self.canvas_offset_x = (canvas_width - display_w) // 2
        self.canvas_offset_y = (canvas_height - display_h) // 2

        self.display_image = self.original_image.resize((display_w, display_h), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(self.display_image)
        
        self.canvas.delete("all")
        self.canvas_image_id = self.canvas.create_image(self.canvas_offset_x, self.canvas_offset_y, anchor=tk.NW, image=self.tk_image)
        self.redraw_all_crops()

    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        coords = (min(x1_img, x2_img), min(y1_img, y2_img), max(x1_img, x2_img), max(y1_img, y2_img)
        if (coords[2] - coords[0]) < MIN_CROP_SIZE or (coords[3] - coords[1]) < MIN_CROP_SIZE:
            return

        crop_id = str(uuid.uuid4())
        base_name = os.path.splitext(os.path.basename(self.image_path))[0] if self.image_path else "Image"
        crop_name = f"{base_name}_Crop_{self.get_next_crop_number()}"

        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])
        rect_id = self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH, tags=(RECT_TAG_PREFIX + crop_id, "crop_rect"))

        self.crops[crop_id] = {'coords': coords, 'name': crop_name, 'rect_id': rect_id}
        self.crop_order.append(crop_id)
        self.crop_listbox.insert(tk.END, crop_name)
        self.select_crop(crop_id, from_listbox=False)
        self.btn_save_crops.configure(state=tk.NORMAL)
        self.btn_delete_crop.configure(state=tk.NORMAL)

    def save_crops(self):
        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        output_dir = os.path.abspath(base_name)
        
        try:
            os.makedirs(output_dir, exist_ok=True)
            for i, crop_id in enumerate(self.crop_order, 1):
                data = self.crops[crop_id]
                coords = tuple(map(int, data['coords']))
                cropped_img = self.original_image.crop(coords)
                if cropped_img.mode in ('RGBA', 'P'):
                    cropped_img = cropped_img.convert('RGB')
                cropped_img.save(os.path.join(output_dir, f"{base_name}_{i}.jpg"), "JPEG", quality=95)
            messagebox.showinfo("Success", f"Crops saved to {output_dir}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save crops:\n{e}")

    # ... (Other existing methods remain mostly the same with minor adjustments for new features)

if __name__ == "__main__":
    app = MultiCropApp()
    app.mainloop()
