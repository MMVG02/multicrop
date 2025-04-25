import tkinter as tk
from tkinter import filedialog, messagebox, Listbox, simpledialog
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid
import math

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

        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.tk_image = None
        self.canvas_image_id = None
        self.crops = {}
        self.selected_crop_id = None
        self.crop_order = []

        self.start_x = None
        self.start_y = None
        self.current_rect_id = None
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.move_offset_x = 0
        self.move_offset_y = 0

        self.zoom_factor = 1.0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_panning = False
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.image_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.image_frame, bg="gray90", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.control_frame = ctk.CTkFrame(self, width=250)
        self.control_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False)
        self.control_frame.grid_rowconfigure(3, weight=1)
        self.control_frame.grid_columnconfigure(0, weight=1)

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
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)

        self.btn_delete_crops = ctk.CTkButton(self.control_frame, text="Delete Selected Crops", command=self.delete_selected_crops,
                                              state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crops.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")

        self.btn_frame = ctk.CTkFrame(self.control_frame)
        self.btn_frame.grid(row=5, column=0, padx=10, pady=5, sticky="ew")
        self.btn_frame.grid_columnconfigure(0, weight=1)
        self.btn_frame.grid_columnconfigure(1, weight=1)

        self.btn_move_up = ctk.CTkButton(self.btn_frame, text="Move Up", command=self.move_up, state=tk.DISABLED)
        self.btn_move_up.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.btn_move_down = ctk.CTkButton(self.btn_frame, text="Move Down", command=self.move_down, state=tk.DISABLED)
        self.btn_move_down.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.btn_rename = ctk.CTkButton(self.control_frame, text="Rename Selected Crop", command=self.rename_selected_crop, state=tk.DISABLED)
        self.btn_rename.grid(row=6, column=0, padx=10, pady=5, sticky="ew")

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1))
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1))
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press)
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.update_cursor)
        self.canvas.bind("<Button-3>", self.on_right_click)
        self.bind("<Delete>", self.delete_selected_crops_event)
        self.bind("<Configure>", self.on_window_resize)

    def select_image(self):
        path = filedialog.askopenfilename(title="Select Image File",
                                          filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff")])
        if not path:
            return
        try:
            self.image_path = path
            self.original_image = Image.open(self.image_path)
            self.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = 600
                canvas_height = 500
            img_width, img_height = self.original_image.size
            if img_width == 0 or img_height == 0:
                raise ValueError("Image has zero dimension")
            zoom_h = canvas_width / img_width
            zoom_v = canvas_height / img_height
            self.zoom_factor = min(1.0, min(zoom_h, zoom_v)) * 0.98
            display_w = img_width * self.zoom_factor
            display_h = img_height * self.zoom_factor
            self.canvas_offset_x = math.ceil((canvas_width - display_w) / 2)
            self.canvas_offset_y = math.ceil((canvas_height - display_h) / 2)
            self.clear_crops_and_list()
            self.display_image_on_canvas()
            self.btn_save_crops.configure(state=tk.DISABLED)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or process image:\n{e}")
            self.image_path = None
            self.original_image = None
            self.clear_crops_and_list()
            self.canvas.delete("all")
            self.tk_image = None
            self.display_image = None
            self.btn_save_crops.configure(state=tk.DISABLED)

    def clear_crops_and_list(self):
        self.canvas.delete("crop_rect")
        self.crops.clear()
        self.crop_listbox.delete(0, tk.END)
        self.crop_order.clear()
        self.selected_crop_id = None
        self.btn_delete_crops.configure(state=tk.DISABLED)

    def display_image_on_canvas(self):
        if not self.original_image:
            self.canvas.delete("all")
            return
        disp_w = max(1, int(self.original_image.width * self.zoom_factor))
        disp_h = max(1, int(self.original_image.height * self.zoom_factor))
        try:
            self.display_image = self.original_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        except Exception as e:
            print(f"Error resizing image: {e}")
            self.display_image = None
            self.canvas.delete("all")
            return
        self.tk_image = ImageTk.PhotoImage(self.display_image)
        self.canvas.delete("all")
        self.canvas_image_id = self.canvas.create_image(int(round(self.canvas_offset_x)), int(round(self.canvas_offset_y)),
                                                        anchor=tk.NW, image=self.tk_image, tags="image")
        self.redraw_all_crops()

    def canvas_to_image_coords(self, canvas_x, canvas_y):
        if not self.original_image or self.zoom_factor == 0:
            return None, None
        img_x = (canvas_x - self.canvas_offset_x) / self.zoom_factor
        img_y = (canvas_y - self.canvas_offset_y) / self.zoom_factor
        return img_x, img_y

    def image_to_canvas_coords(self, img_x, img_y):
        if not self.original_image:
            return None, None
        canvas_x = (img_x * self.zoom_factor) + self.canvas_offset_x
        canvas_y = (img_y * self.zoom_factor) + self.canvas_offset_y
        return canvas_x, canvas_y

    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        if not self.original_image:
            return
        img_w, img_h = self.original_image.size
        x1_img = max(0, min(x1_img, img_w))
        y1_img = max(0, min(y1_img, img_h))
        x2_img = max(0, min(x2_img, img_w))
        y2_img = max(0, min(y2_img, img_h))
        if abs(x2_img - x1_img) < MIN_CROP_SIZE or abs(y2_img - y1_img) < MIN_CROP_SIZE:
            print("Crop too small, ignoring.")
            if self.current_rect_id:
                self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            return
        coords = (min(x1_img, x2_img), min(y1_img, y2_img), max(x1_img, x2_img), max(y1_img, y2_img))
        crop_id = str(uuid.uuid4())
        base_name = "Image" if not self.image_path else os.path.splitext(os.path.basename(self.image_path))[0]
        used_numbers = set()
        for data in self.crops.values():
            name = data['name']
            if name.startswith(base_name + "Crop"):
                try:
                    num = int(name[len(base_name + "Crop"):])
                    used_numbers.add(num)
                except ValueError:
                    pass
        n = 1
        while n in used_numbers:
            n += 1
        crop_name = f"{base_name}Crop{n}"
        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])
        if cx1 is None:
            print("Error: Cannot draw crop, coordinate conversion failed.")
            return
        rect_id = self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH,
                                               tags=(RECT_TAG_PREFIX + crop_id, "crop_rect"))
        self.crops[crop_id] = {'coords': coords, 'name': crop_name, 'rect_id': rect_id}
        self.crop_listbox.insert(tk.END, crop_name)
        self.crop_order.append(crop_id)
        self.crop_listbox.selection_clear(0, tk.END)
        self.crop_listbox.selection_set(tk.END)
        self.select_crop(crop_id, from_listbox=False)
        self.btn_save_crops.configure(state=tk.NORMAL)
        self.btn_delete_crops.configure(state=tk.NORMAL)

    def select_crop(self, crop_id, from_listbox=True):
        if self.selected_crop_id == crop_id and crop_id is not None:
            return
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            prev_rect_id = self.crops[self.selected_crop_id]['rect_id']
            if prev_rect_id in self.canvas.find_withtag(prev_rect_id):
                self.canvas.itemconfig(prev_rect_id, outline=DEFAULT_RECT_COLOR)
        self.selected_crop_id = crop_id
        if crop_id and crop_id in self.crops:
            rect_id = self.crops[crop_id]['rect_id']
            if rect_id in self.canvas.find_withtag(rect_id):
                self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR)
                self.canvas.tag_raise(rect_id)
                self.btn_delete_crops.configure(state=tk.NORMAL)
                if not from_listbox:
                    index = self.crop_order.index(crop_id)
                    self.crop_listbox.selection_clear(0, tk.END)
                    self.crop_listbox.selection_set(index)
                    self.crop_listbox.activate(index)
                    self.crop_listbox.see(index)
            else:
                self.selected_crop_id = None
                self.btn_delete_crops.configure(state=tk.DISABLED)
        else:
            self.selected_crop_id = None
            if not from_listbox:
                self.crop_listbox.selection_clear(0, tk.END)
            self.btn_delete_crops.configure(state=tk.DISABLED)

    def update_crop_coords(self, crop_id, new_img_coords):
        if crop_id in self.crops and self.original_image:
            img_w, img_h = self.original_image.size
            x1, y1, x2, y2 = new_img_coords
            x1 = max(0, min(x1, img_w))
            y1 = max(0, min(y1, img_h))
            x2 = max(0, min(x2, img_w))
            y2 = max(0, min(y2, img_h))
            final_x1 = min(x1, x2)
            final_y1 = min(y1, y2)
            final_x2 = max(x1, x2)
            final_y2 = max(y1, y2)
            if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE:
                print("Debug: Crop update rejected due to min size violation")
                return False
            self.crops[crop_id]['coords'] = (final_x1, final_y1, final_x2, final_y2)
            return True
        return False

    def redraw_all_crops(self):
        all_canvas_items = self.canvas.find_all()
        for crop_id, data in self.crops.items():
            img_x1, img_y1, img_x2, img_y2 = data['coords']
            cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1)
            cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)
            if cx1 is None:
                continue
            color = SELECTED_RECT_COLOR if crop_id == self.selected_crop_id else DEFAULT_RECT_COLOR
            tags_tuple = (RECT_TAG_PREFIX + crop_id, "crop_rect")
            if data['rect_id'] in all_canvas_items:
                self.canvas.coords(data['rect_id'], cx1, cy1, cx2, cy2)
                self.canvas.itemconfig(data['rect_id'], outline=color, tags=tags_tuple)
            else:
                rect_id = self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=color, width=RECT_WIDTH, tags=tags_tuple)
                self.crops[crop_id]['rect_id'] = rect_id
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            selected_rect_id = self.crops[self.selected_crop_id]['rect_id']
            if selected_rect_id in self.canvas.find_all():
                self.canvas.tag_raise(selected_rect_id)

    def delete_selected_crops(self):
        selected_indices = self.crop_listbox.curselection()
        if not selected_indices:
            return
        crop_ids_to_delete = [self.crop_order[index] for index in selected_indices]
        for crop_id in crop_ids_to_delete:
            data = self.crops[crop_id]
            if data['rect_id'] in self.canvas.find_all():
                self.canvas.delete(data['rect_id'])
            del self.crops[crop_id]
            self.crop_order.remove(crop_id)
        for index in sorted(selected_indices, reverse=True):
            self.crop_listbox.delete(index)
        self.selected_crop_id = None
        self.btn_delete_crops.configure(state=tk.DISABLED)
        if not self.crops:
            self.btn_save_crops.configure(state=tk.DISABLED)

    def delete_selected_crops_event(self, event=None):
        self.delete_selected_crops()

    def move_up(self):
        selection = self.crop_listbox.curselection()
        if len(selection) != 1:
            return
        index = selection[0]
        if index == 0:
            return
        prev_index = index - 1
        item = self.crop_listbox.get(index)
        self.crop_listbox.delete(index)
        self.crop_listbox.insert(prev_index, item)
        self.crop_order[prev_index], self.crop_order[index] = self.crop_order[index], self.crop_order[prev_index]
        self.crop_listbox.selection_clear(0, tk.END)
        self.crop_listbox.selection_set(prev_index)
        self.crop_listbox.activate(prev_index)
        self.crop_listbox.see(prev_index)
        self.on_listbox_select()

    def move_down(self):
        selection = self.crop_listbox.curselection()
        if len(selection) != 1:
            return
        index = selection[0]
        if index == self.crop_listbox.size() - 1:
            return
        next_index = index + 1
        item = self.crop_listbox.get(index)
        self.crop_listbox.delete(index)
        self.crop_listbox.insert(next_index, item)
        self.crop_order[index], self.crop_order[next_index] = self.crop_order[next_index], self.crop_order[index]
        self.crop_listbox.selection_clear(0, tk.END)
        self.crop_listbox.selection_set(next_index)
        self.crop_listbox.activate(next_index)
        self.crop_listbox.see(next_index)
        self.on_listbox_select()

    def rename_selected_crop(self):
        selection = self.crop_listbox.curselection()
        if len(selection) != 1:
            messagebox.showwarning("Selection Error", "Please select exactly one crop to rename.")
            return
        index = selection[0]
        crop_id = self.crop_order[index]
        current_name = self.crops[crop_id]['name']
        new_name = simpledialog.askstring("Rename Crop", "Enter new name:", initialvalue=current_name)
        if new_name and new_name != current_name:
            self.crops[crop_id]['name'] = new_name
            self.crop_listbox.delete(index)
            self.crop_listbox.insert(index, new_name)
            self.crop_listbox.selection_set(index)

    def on_right_click(self, event):
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        overlapping_items = self.canvas.find_overlapping(canvas_x-1, canvas_y-1, canvas_x+1, canvas_y+1)
        for item_id in reversed(overlapping_items):
            tags = self.canvas.gettags(item_id)
            if tags and tags[0].startswith(RECT_TAG_PREFIX) and "crop_rect" in tags:
                crop_id = tags[0][len(RECT_TAG_PREFIX):]
                if crop_id in self.crops:
                    self.select_crop(crop_id)
                    break

    def on_listbox_select(self, event=None):
        selection = self.crop_listbox.curselection()
        if len(selection) == 1:
            index = selection[0]
            crop_id = self.crop_order[index]
            self.select_crop(crop_id, from_listbox=True)
            self.btn_rename.configure(state=tk.NORMAL)
            self.btn_move_up.configure(state=tk.NORMAL if index > 0 else tk.DISABLED)
            self.btn_move_down.configure(state=tk.NORMAL if index < self.crop_listbox.size() - 1 else tk.DISABLED)
        else:
            self.btn_rename.configure(state=tk.DISABLED)
            self.btn_move_up.configure(state=tk.DISABLED)
            self.btn_move_down.configure(state=tk.DISABLED)
        if selection:
            self.btn_delete_crops.configure(state=tk.NORMAL)
        else:
            self.btn_delete_crops.configure(state=tk.DISABLED)

    def on_mouse_press(self, event):
        self.canvas.focus_set()
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        handle = self.get_resize_handle(canvas_x, canvas_y)
        if handle and self.selected_crop_id:
            self.is_resizing = True
            self.resize_handle = handle
            self.start_x = canvas_x
            self.start_y = canvas_y
            self.start_coords_img = self.crops[self.selected_crop_id]['coords']
            return
        overlapping_items = self.canvas.find_overlapping(canvas_x-1, canvas_y-1, canvas_x+1, canvas_y+1)
        clicked_crop_id = None
        for item_id in reversed(overlapping_items):
            tags = self.canvas.gettags(item_id)
            if tags and tags[0].startswith(RECT_TAG_PREFIX) and "crop_rect" in tags:
                crop_id = tags[0][len(RECT_TAG_PREFIX):]
                if crop_id in self.crops:
                    clicked_crop_id = crop_id
                    break
        if clicked_crop_id:
            self.select_crop(clicked_crop_id)
            self.is_moving = True
            rect_coords = self.canvas.coords(self.crops[clicked_crop_id]['rect_id'])
            self.move_offset_x = canvas_x - rect_coords[0]
            self.move_offset_y = canvas_y - rect_coords[1]
            return
        if self.original_image:
            self.is_drawing = True
            self.start_x = canvas_x
            self.start_y = canvas_y
            self.current_rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y,
                                                               outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4),
                                                               tags=("temp_rect",))
            self.select_crop(None)

    def on_mouse_drag(self, event):
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if self.is_drawing and self.current_rect_id:
            self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)
        elif self.is_moving and self.selected_crop_id:
            crop_id = self.selected_crop_id
            rect_id = self.crops[crop_id]['rect_id']
            current_canvas_coords = self.canvas.coords(rect_id)
            w = current_canvas_coords[2] - current_canvas_coords[0]
            h = current_canvas_coords[3] - current_canvas_coords[1]
            new_cx1 = canvas_x - self.move_offset_x
            new_cy1 = canvas_y - self.move_offset_y
            new_cx2 = new_cx1 + w
            new_cy2 = new_cy1 + h
            img_x1, img_y1 = self.canvas_to_image_coords(new_cx1, new_cy1)
            img_x2, img_y2 = self.canvas_to_image_coords(new_cx2, new_cy2)
            if img_x1 is not None:
                if self.update_crop_coords(crop_id, (img_x1, img_y1, img_x2, img_y2)):
                    validated_img_coords = self.crops[crop_id]['coords']
                    cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                    cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                    self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)
        elif self.is_resizing and self.selected_crop_id and self.resize_handle:
            crop_id = self.selected_crop_id
            rect_id = self.crops[crop_id]['rect_id']
            ox1_img, oy1_img, ox2_img, oy2_img = self.start_coords_img
            curr_img_x, curr_img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            start_img_x, start_img_y = self.canvas_to_image_coords(self.start_x, self.start_y)
            if curr_img_x is None or start_img_x is None:
                return
            dx_img = curr_img_x - start_img_x
            dy_img = curr_img_y - start_img_y
            nx1, ny1, nx2, ny2 = ox1_img, oy1_img, ox2_img, oy2_img
            if 'n' in self.resize_handle: ny1 += dy_img
            if 's' in self.resize_handle: ny2 += dy_img
            if 'w' in self.resize_handle: nx1 += dx_img
            if 'e' in self.resize_handle: nx2 += dx_img
            if self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2)):
                validated_img_coords = self.crops[crop_id]['coords']
                cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)

    def on_mouse_release(self, event):
        if self.is_drawing and self.current_rect_id:
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            if self.current_rect_id in self.canvas.find_withtag("temp_rect"):
                self.canvas.delete(self.current_rect_id)
            img_x1, img_y1 = self.canvas_to_image_coords(self.start_x, self.start_y)
            img_x2, img_y2 = self.canvas_to_image_coords(canvas_x, canvas_y)
            if all(v is not None for v in [img_x1, img_y1, img_x2, img_y2]):
                self.add_crop(img_x1, img_y1, img_x2, img_y2)
            else:
                print("Failed to add crop due to coordinate conversion error.")
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.current_rect_id = None
        self.update_cursor(event)

    def on_mouse_wheel(self, event, direction=None):
        if not self.original_image:
            return
        delta = direction if direction else (-1 if event.num == 5 or event.delta < 0 else 1 if event.num == 4 or event.delta > 0 else 0)
        if delta == 0:
            return
        zoom_increment = 1.1
        min_zoom, max_zoom = 0.01, 20.0
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        img_x_before, img_y_before = self.canvas_to_image_coords(canvas_x, canvas_y)
        if img_x_before is None:
            return
        new_zoom = self.zoom_factor * zoom_increment if delta > 0 else self.zoom_factor / zoom_increment
        self.zoom_factor = max(min_zoom, min(max_zoom, new_zoom))
        if new_zoom == self.zoom_factor:
            return
        self.canvas_offset_x = canvas_x - (img_x_before * self.zoom_factor)
        self.canvas_offset_y = canvas_y - (img_y_before * self.zoom_factor)
        self.display_image_on_canvas()

    def on_pan_press(self, event):
        if not self.original_image:
            return
        self.is_panning = True
        self.pan_start_x = self.canvas.canvasx(event.x)
        self.pan_start_y = self.canvas.canvasy(event.y)
        self.canvas.config(cursor="fleur")

    def on_pan_drag(self, event):
        if not self.is_panning or not self.original_image:
            return
        current_x = self.canvas.canvasx(event.x)
        current_y = self.canvas.canvasy(event.y)
        dx = current_x - self.pan_start_x
        dy = current_y - self.pan_start_y
        self.canvas_offset_x += dx
        self.canvas_offset_y += dy
        self.canvas.move("all", dx, dy)
        self.pan_start_x = current_x
        self.pan_start_y = current_y

    def on_pan_release(self, event):
        self.is_panning = False
        self.update_cursor(event)

    def get_resize_handle(self, canvas_x, canvas_y):
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            return None
        rect_id = self.crops[self.selected_crop_id]['rect_id']
        if rect_id not in self.canvas.find_all():
            return None
        cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
        handle_margin = 6
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'nw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'ne'
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'sw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'se'
        inner_buffer = handle_margin / 2
        if abs(canvas_y - cy1) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 'n'
        if abs(canvas_y - cy2) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 's'
        if abs(canvas_x - cx1) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'w'
        if abs(canvas_x - cx2) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'e'
        return None

    def update_cursor(self, event=None):
        if self.is_panning or self.is_moving:
            self.canvas.config(cursor="fleur")
            return
        if self.is_drawing or self.is_resizing:
            return
        new_cursor = ""
        if event:
            canvas_x = self.canvas.canvasx(event.x)
            canvas_y = self.canvas.canvasy(event.y)
            handle = self.get_resize_handle(canvas_x, canvas_y)
            if handle:
                if handle in ('nw', 'se'): new_cursor = "size_nw_se"
                elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
                elif handle in ('n', 's'): new_cursor = "size_ns"
                elif handle in ('e', 'w'): new_cursor = "size_we"
            elif self.selected_crop_id and self.selected_crop_id in self.crops:
                rect_id = self.crops[self.selected_crop_id]['rect_id']
                if rect_id in self.canvas.find_all():
                    cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
                    if cx1 < canvas_x < cx2 and cy1 < canvas_y < cy2:
                        new_cursor = "fleur"
        if self.canvas.cget("cursor") != new_cursor:
            self.canvas.config(cursor=new_cursor)

    def on_window_resize(self, event=None):
        pass

    def save_crops(self):
        if not self.original_image or not self.image_path:
            messagebox.showwarning("No Image", "Please select an image first.")
            return
        if not self.crops:
            messagebox.showwarning("No Crops", "Please define at least one crop area.")
            return
        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        output_dir = os.path.abspath(base_name)
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Directory Error", f"Could not create output directory:\n{output_dir}\n{e}")
            return
        saved_count = 0
        error_count = 0
        for i, crop_id in enumerate(self.crop_order, start=1):
            if crop_id not in self.crops:
                continue
            data = self.crops[crop_id]
            coords = tuple(map(int, data['coords']))
            filename = f"{base_name}_{i}.jpg"
            filepath = os.path.join(output_dir, filename)
            try:
                cropped_img = self.original_image.crop(coords)
                if cropped_img.mode in ('RGBA', 'P'):
                    cropped_img = cropped_img.convert('RGB')
                cropped_img.save(filepath, "JPEG", quality=95)
                saved_count += 1
            except Exception as e:
                error_count += 1
                print(f"Error saving {filename}: {e}")
        if error_count == 0:
            messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to the '{base_name}' folder.")
        else:
            messagebox.showwarning("Partial Success", f"Saved {saved_count} crops to '{base_name}'.\nFailed to save {error_count} crops.")

if __name__ == "__main__":
    app = MultiCropApp()
    app.mainloop()
