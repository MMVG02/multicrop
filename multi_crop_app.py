import tkinter as tk
from tkinter import filedialog, messagebox, Listbox, simpledialog
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid
import math
import sys
import re # Import regex

# --- Constants ---
RECT_TAG_PREFIX = "crop_rect_"
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
MIN_CROP_SIZE = 10
RESIZE_HANDLE_MARGIN = 6

# --- Main Application Class ---
class MultiCropApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Multi Image Cropper")
        self.geometry("1000x700")
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        # --- State Variables ---
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.tk_image = None
        self.canvas_image_id = None

        # Crop Data and Order
        self.crops = {}            # {crop_id: {'coords': (x1,y1,x2,y2), 'name': name, 'rect_id': canvas_rect_id}}
        self.crop_order = []       # List of crop_ids in the desired user order
        self.selected_crop_id = None # Currently selected single crop ID for canvas editing

        # Drawing/Editing State
        self.start_x = None
        self.start_y = None
        self.current_rect_id = None # ID of the temporary drawing rectangle
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.start_coords_img = None # Store image coords when starting move/resize
        self.start_coords_canvas = None # Store canvas coords when starting move

        # Zoom/Pan State
        self.zoom_factor = 1.0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_panning = False
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0

        # Listbox Drag/Drop State
        self.is_dragging_listbox = False
        self.drag_start_index = None
        self.drag_item_id = None

        # --- UI Layout ---
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Left Frame (Image Display) ---
        self.image_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.image_frame, bg="gray90", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # --- Right Frame (Controls) ---
        self.control_frame = ctk.CTkFrame(self, width=250)
        self.control_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False)
        self.control_frame.grid_rowconfigure(3, weight=1)
        self.control_frame.grid_columnconfigure(0, weight=1)

        # Buttons
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image", command=self.select_image)
        self.btn_select_image.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        self.btn_save_crops = ctk.CTkButton(self.control_frame, text="Save All Crops", command=self.save_crops, state=tk.DISABLED)
        self.btn_save_crops.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        # Crop List Label
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List (Drag to reorder, Double-click to rename):")
        self.lbl_crop_list.grid(row=2, column=0, padx=10, pady=(10, 0), sticky="w")

        # Crop Listbox
        self.crop_listbox = Listbox(self.control_frame,
                                    bg='white', fg='black',
                                    selectbackground='#CDEAFE',
                                    selectforeground='black',
                                    highlightthickness=1, highlightbackground="#CCCCCC",
                                    highlightcolor="#89C4F4",
                                    borderwidth=0, exportselection=False,
                                    selectmode=tk.EXTENDED)
        self.crop_listbox.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")

        # Bindings for Listbox
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.crop_listbox.bind("<Double-Button-1>", self.on_listbox_double_click)
        self.crop_listbox.bind("<ButtonPress-1>", self.on_listbox_press)
        self.crop_listbox.bind("<B1-Motion>", self.on_listbox_drag)
        self.crop_listbox.bind("<ButtonRelease-1>", self.on_listbox_release)

        # Delete Button
        self.btn_delete_crops = ctk.CTkButton(self.control_frame, text="Delete Selected Crops", command=self.delete_selected_crops, state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crops.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")

        # --- Canvas Bindings ---
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1)) # Linux scroll up
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1)) # Linux scroll down
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press) # Middle mouse
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.update_cursor)
        self.bind("<Delete>", self.delete_selected_crops_event)
        self.canvas.bind("<Configure>", self.on_canvas_configure)

    # --- Image Handling ---
    def select_image(self):
        path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff")]
        )
        if not path:
            return

        try:
            if self.crops:
                if messagebox.askyesno("Save Current Work", "You have unsaved crops. Do you want to save them before opening a new image?"):
                     self.save_crops()

            self.image_path = path
            self.original_image = Image.open(self.image_path)

            self.clear_crops_and_list() # Clears all crop data

            self.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            if canvas_width <= 1 or canvas_height <= 1:
                 canvas_width = 800
                 canvas_height = 600

            img_width, img_height = self.original_image.size
            if img_width == 0 or img_height == 0:
                 raise ValueError("Image has zero dimension")

            padding_factor = 0.98
            zoom_h = (canvas_width * padding_factor) / img_width
            zoom_v = (canvas_height * padding_factor) / img_height
            self.zoom_factor = min(1.0, min(zoom_h, zoom_v))

            display_w = img_width * self.zoom_factor
            display_h = img_height * self.zoom_factor
            self.canvas_offset_x = math.ceil((canvas_width - display_w) / 2)
            self.canvas_offset_y = math.ceil((canvas_height - display_h) / 2)

            self.display_image_on_canvas()
            self.btn_save_crops.configure(state=tk.DISABLED)
            self.btn_delete_crops.configure(state=tk.DISABLED)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or process image:\n{e}")
            self.image_path = None
            self.original_image = None
            self.clear_crops_and_list()
            self.canvas.delete("all")
            self.tk_image = None
            self.display_image = None
            self.btn_save_crops.configure(state=tk.DISABLED)
            self.btn_delete_crops.configure(state=tk.DISABLED)

    def clear_crops_and_list(self):
        """Clears existing crops, listbox, and resets related states."""
        self.canvas.delete("crop_rect")
        self.crops.clear()
        self.crop_order.clear()
        self.refresh_listbox()
        self.selected_crop_id = None
        self.btn_delete_crops.configure(state=tk.DISABLED)

    def display_image_on_canvas(self):
        """Displays the current self.display_image on the canvas respecting zoom and pan."""
        if not self.original_image:
            self.canvas.delete("all")
            return

        disp_w = int(self.original_image.width * self.zoom_factor)
        disp_h = int(self.original_image.height * self.zoom_factor)

        disp_w = max(1, disp_w)
        disp_h = max(1, disp_h)

        try:
            self.display_image = self.original_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        except Exception as e:
             print(f"Error resizing image: {e}")
             self.display_image = None
             self.canvas.delete("all")
             return

        self.tk_image = ImageTk.PhotoImage(self.display_image)

        self.canvas.delete("image")
        self.canvas.delete("crop_rect")

        int_offset_x = int(round(self.canvas_offset_x))
        int_offset_y = int(round(self.canvas_offset_y))

        self.canvas_image_id = self.canvas.create_image(
            int_offset_x, int_offset_y,
            anchor=tk.NW, image=self.tk_image, tags="image"
        )

        self.redraw_all_crops()

    # --- Coordinate Conversion ---
    def canvas_to_image_coords(self, canvas_x, canvas_y):
        """Convert canvas coordinates to original image coordinates."""
        if not self.original_image or self.zoom_factor == 0: return None, None
        img_x = (canvas_x - self.canvas_offset_x) / self.zoom_factor
        img_y = (canvas_y - self.canvas_offset_y) / self.zoom_factor

        img_width, img_height = self.original_image.size
        img_x = max(0, min(img_x, img_width))
        img_y = max(0, min(img_y, img_height))

        return img_x, img_y

    def image_to_canvas_coords(self, img_x, img_y):
        """Convert original image coordinates to canvas coordinates."""
        if not self.original_image: return None, None
        canvas_x = (img_x * self.zoom_factor) + self.canvas_offset_x
        canvas_y = (img_y * self.zoom_factor) + self.canvas_offset_y
        return canvas_x, canvas_y

    # --- Crop Handling ---
    def find_next_default_crop_number(self):
        """Finds the smallest positive integer not currently used in default crop names."""
        used_numbers = set()
        # Regex to find a number at the end, optionally preceded by common separators and 'crop'
        # More robust: look for a number at the end preceded by non-digits
        # Simple version: look for '_number' or 'number' at the end
        pattern = re.compile(r'_?(\d+)$') # Matches _123 or 123 at the end

        for crop_data in self.crops.values():
            name = crop_data['name']
            match = pattern.search(name)
            if match:
                try:
                    number = int(match.group(1))
                    used_numbers.add(number)
                except ValueError:
                    pass # Ignore names that look like they end in a number but aren't parseable

        n = 1
        while n in used_numbers:
            n += 1
        return n


    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        """Adds a new crop definition, adds it to the order, and redraws."""
        if not self.original_image: return

        img_w, img_h = self.original_image.size

        x1_img = max(0.0, min(x1_img, img_w))
        y1_img = max(0.0, min(y1_img, img_h))
        x2_img = max(0.0, min(x2_img, img_w))
        y2_img = max(0.0, min(y2_img, img_h))

        final_x1 = min(x1_img, x2_img)
        final_y1 = min(y1_img, y2_img)
        final_x2 = max(x1_img, x2_img)
        final_y2 = max(y1_img, y2_img)

        if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE:
            return

        coords = (final_x1, final_y1, final_x2, final_y2)

        crop_id = str(uuid.uuid4())
        base_name = os.path.splitext(os.path.basename(self.image_path))[0] if self.image_path else "Image"

        # Use the calculated next available number for the default name
        next_num = self.find_next_default_crop_number()
        crop_name = f"{base_name}_Crop_{next_num}"

        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])

        if cx1 is None:
             print("Error: Cannot add crop, coordinate conversion failed.")
             return

        rect_id = self.canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH,
            tags=(RECT_TAG_PREFIX + crop_id, "crop_rect")
        )

        self.crops[crop_id] = {
            'coords': coords,
            'name': crop_name,
            'rect_id': rect_id
        }
        self.crop_order.append(crop_id)

        self.refresh_listbox()
        new_index = len(self.crop_order) - 1
        if new_index >= 0:
            self.crop_listbox.selection_clear(0, tk.END)
            self.crop_listbox.selection_set(new_index)
            self.crop_listbox.activate(new_index)
            self.crop_listbox.see(new_index)
            self.select_crop(crop_id, from_listbox=False)

        self.btn_save_crops.configure(state=tk.NORMAL)
        # Delete button state handled by on_listbox_select

    def select_crop(self, crop_id, from_listbox=False):
        """Selects a crop by its ID, updates visuals on canvas."""
        if self.selected_crop_id and self.selected_crop_id in self.crops:
             prev_rect_id = self.crops[self.selected_crop_id]['rect_id']
             if self.canvas.find_withtag(prev_rect_id):
                  self.canvas.itemconfig(prev_rect_id, outline=DEFAULT_RECT_COLOR)

        self.selected_crop_id = crop_id

        if crop_id and crop_id in self.crops:
            rect_id = self.crops[crop_id]['rect_id']
            if self.canvas.find_withtag(rect_id):
                 self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR)
                 self.canvas.tag_raise(rect_id)

                 if not from_listbox:
                      try:
                          index = self.crop_order.index(crop_id)
                          self.crop_listbox.selection_clear(0, tk.END)
                          self.crop_listbox.selection_set(index)
                          self.crop_listbox.activate(index)
                          self.crop_listbox.see(index)
                      except ValueError:
                           print(f"Error: crop_id {crop_id} not found in crop_order.")
                           self.crop_listbox.selection_clear(0, tk.END)
                           self.selected_crop_id = None

            else:
                 print(f"Warning: Stale rectangle ID {rect_id} for crop {crop_id}")
                 if crop_id in self.crops:
                      del self.crops[crop_id]
                 if crop_id in self.crop_order:
                      self.crop_order.remove(crop_id)
                 self.refresh_listbox()
                 self.selected_crop_id = None

        else:
            self.selected_crop_id = None
            if not from_listbox:
                 self.crop_listbox.selection_clear(0, tk.END)

    def update_crop_coords(self, crop_id, new_img_coords):
        """Updates the stored original image coordinates for a crop."""
        if crop_id in self.crops and self.original_image:
             img_w, img_h = self.original_image.size
             x1, y1, x2, y2 = new_img_coords

             x1 = max(0.0, min(x1, img_w))
             y1 = max(0.0, min(y1, img_h))
             x2 = max(0.0, min(x2, img_w))
             y2 = max(0.0, min(y2, img_h))

             sorted_x1, sorted_x2 = sorted((x1, x2))
             sorted_y1, sorted_y2 = sorted((y1, y2))

             if (sorted_x2 - sorted_x1) < MIN_CROP_SIZE or (sorted_y2 - sorted_y1) < MIN_CROP_SIZE:
                 return False

             self.crops[crop_id]['coords'] = (sorted_x1, sorted_y1, sorted_x2, sorted_y2)
             return True
        return False

    def redraw_all_crops(self):
        """Redraws all rectangles based on stored coords and current view."""
        self.canvas.delete("crop_rect")

        for crop_id in self.crop_order:
            if crop_id in self.crops:
                 data = self.crops[crop_id]
                 img_x1, img_y1, img_x2, img_y2 = data['coords']

                 cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1)
                 cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)

                 if cx1 is None: continue

                 color = SELECTED_RECT_COLOR if crop_id == self.selected_crop_id else DEFAULT_RECT_COLOR
                 tags_tuple = (RECT_TAG_PREFIX + crop_id, "crop_rect")

                 rect_id = self.canvas.create_rectangle(
                      cx1, cy1, cx2, cy2,
                      outline=color, width=RECT_WIDTH,
                      tags=tags_tuple
                 )
                 self.crops[crop_id]['rect_id'] = rect_id

        if self.selected_crop_id and self.selected_crop_id in self.crops:
            selected_rect_id = self.crops[self.selected_crop_id]['rect_id']
            if self.canvas.find_withtag(selected_rect_id):
                 self.canvas.tag_raise(selected_rect_id)

    def refresh_listbox(self):
        """Clears the listbox and repopulates it based on self.crop_order."""
        self.crop_listbox.delete(0, tk.END)
        for crop_id in self.crop_order:
            if crop_id in self.crops:
                self.crop_listbox.insert(tk.END, self.crops[crop_id]['name'])
            else:
                print(f"Warning: crop_id {crop_id} found in crop_order but not in crops dictionary!")

        self.select_crop(None, from_listbox=False) # Deselect canvas selection

    def delete_selected_crops_event(self, event=None):
        """Handles delete key press."""
        self.delete_selected_crops()

    def delete_selected_crops(self):
        """Deletes the currently selected crops from the listbox."""
        selected_indices = list(self.crop_listbox.curselection())
        if not selected_indices:
            return

        crop_ids_to_delete = [self.crop_order[i] for i in selected_indices if i < len(self.crop_order)]

        if not crop_ids_to_delete:
             print("Warning: No valid crops found for deletion based on listbox selection.")
             return

        if len(crop_ids_to_delete) > 1:
            if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete {len(crop_ids_to_delete)} selected crops?"):
                return

        # Iterate in reverse order of index to avoid index issues when removing from crop_order list
        for index in sorted(selected_indices, reverse=True):
            if index < len(self.crop_order):
                crop_id = self.crop_order[index]
                if crop_id in self.crops:
                    data = self.crops[crop_id]
                    if self.canvas.find_withtag(data['rect_id']):
                        self.canvas.delete(data['rect_id'])
                    del self.crops[crop_id]
                del self.crop_order[index]

        self.refresh_listbox()
        self.selected_crop_id = None
        self.crop_listbox.selection_clear(0, tk.END)
        self.btn_delete_crops.configure(state=tk.DISABLED)

        if not self.crops:
             self.btn_save_crops.configure(state=tk.DISABLED)

    # --- Mouse Event Handlers (Canvas) ---
    def on_mouse_press(self, event):
        self.canvas.focus_set()
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.selected_crop_id:
            handle = self.get_resize_handle(canvas_x, canvas_y)
            if handle:
                self.is_resizing = True
                self.resize_handle = handle
                self.start_x = canvas_x
                self.start_y = canvas_y
                self.start_coords_img = self.crops[self.selected_crop_id]['coords']
                self.canvas.config(cursor=self.get_handle_cursor(handle))
                return

        if self.selected_crop_id:
             rect_id = self.crops[self.selected_crop_id]['rect_id']
             if self.canvas.find_withtag(rect_id):
                  cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
                  if cx1 <= canvas_x <= cx2 and cy1 <= canvas_y <= cy2:
                       self.is_moving = True
                       self.start_x = canvas_x
                       self.start_y = canvas_y
                       self.start_coords_canvas = self.canvas.coords(rect_id)
                       self.canvas.config(cursor="fleur")
                       return

        tolerance = 3
        items = self.canvas.find_overlapping(canvas_x - tolerance, canvas_y - tolerance, canvas_x + tolerance, canvas_y + tolerance)

        clicked_crop_id = None
        for item_id in reversed(items):
            tags = self.canvas.gettags(item_id)
            for tag in tags:
                if tag.startswith(RECT_TAG_PREFIX):
                    crop_id = tag[len(RECT_TAG_PREFIX):]
                    if crop_id in self.crops:
                         cx1, cy1, cx2, cy2 = self.canvas.coords(item_id)
                         if (cx1 <= canvas_x <= cx2 and cy1 <= canvas_y <= cy2) or \
                            (abs(canvas_x - cx1) <= tolerance) or (abs(canvas_x - cx2) <= tolerance) or \
                            (abs(canvas_y - cy1) <= tolerance) or (abs(canvas_y - cy2) <= tolerance) :
                              clicked_crop_id = crop_id
                              break
            if clicked_crop_id:
                 break

        if clicked_crop_id:
            self.select_crop(clicked_crop_id)
            return

        if self.original_image:
             self.is_drawing = True
             self.start_x = canvas_x
             self.start_y = canvas_y
             self.select_crop(None)
             self.current_rect_id = self.canvas.create_rectangle(
                 self.start_x, self.start_y, self.start_x, self.start_y,
                 outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4),
                 tags=("temp_rect",)
             )

    def on_canvas_double_click(self, event):
        """Handle double-click on canvas - primarily for selecting a rectangle."""
        self.canvas.focus_set()
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        tolerance = 3
        items = self.canvas.find_overlapping(canvas_x - tolerance, canvas_y - tolerance, canvas_x + tolerance, canvas_y + tolerance)

        clicked_crop_id = None
        for item_id in reversed(items):
            tags = self.canvas.gettags(item_id)
            for tag in tags:
                if tag.startswith(RECT_TAG_PREFIX):
                    crop_id = tag[len(RECT_TAG_PREFIX):]
                    if crop_id in self.crops:
                         cx1, cy1, cx2, cy2 = self.canvas.coords(item_id)
                         if (cx1 <= canvas_x <= cx2 and cy1 <= canvas_y <= cy2) or \
                            (abs(canvas_x - cx1) <= tolerance) or (abs(canvas_x - cx2) <= tolerance) or \
                            (abs(canvas_y - cy1) <= tolerance) or (abs(canvas_y - cy2) <= tolerance) :
                              clicked_crop_id = crop_id
                              break
            if clicked_crop_id:
                 break

        if clicked_crop_id:
            self.select_crop(clicked_crop_id)

    def on_mouse_drag(self, event):
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.is_drawing and self.current_rect_id:
            if self.canvas_image_id:
                 img_bbox_canvas = self.canvas.bbox(self.canvas_image_id)
                 if img_bbox_canvas:
                      min_cx, min_cy, max_cx, max_cy = img_bbox_canvas
                      clamped_canvas_x = max(min_cx, min(canvas_x, max_cx))
                      clamped_canvas_y = max(min_cy, min(canvas_y, max_cy))
                      self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, clamped_canvas_x, clamped_canvas_y)
                 else:
                      self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)
            else:
                 self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)

        elif self.is_moving and self.selected_crop_id and self.start_coords_canvas:
            crop_id = self.selected_crop_id
            rect_id = self.crops[crop_id]['rect_id']

            dx = canvas_x - self.start_x
            dy = canvas_y - self.start_y

            new_cx1 = self.start_coords_canvas[0] + dx
            new_cy1 = self.start_coords_canvas[1] + dy
            new_cx2 = self.start_coords_canvas[2] + dx
            new_cy2 = self.start_coords_canvas[3] + dy

            img_x1, img_y1 = self.canvas_to_image_coords(new_cx1, new_cy1)
            img_x2, img_y2 = self.canvas_to_image_coords(new_cx2, new_cy2)

            if img_x1 is not None:
                 updated = self.update_crop_coords(crop_id, (img_x1, img_y1, img_x2, img_y2))
                 if updated:
                      validated_img_coords = self.crops[crop_id]['coords']
                      cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                      cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                      self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)

        elif self.is_resizing and self.selected_crop_id and self.resize_handle and self.start_coords_img:
            crop_id = self.selected_crop_id
            rect_id = self.crops[crop_id]['rect_id']

            ox1_img, oy1_img, ox2_img, oy2_img = self.start_coords_img

            curr_img_x, curr_img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            start_img_x, start_img_y = self.canvas_to_image_coords(self.start_x, self.start_y)

            if curr_img_x is None or start_img_x is None: return

            dx_img = curr_img_x - start_img_x
            dy_img = curr_img_y - start_img_y

            nx1, ny1, nx2, ny2 = ox1_img, oy1_img, ox2_img, oy2_img

            if 'n' in self.resize_handle: ny1 = oy1_img + dy_img
            if 's' in self.resize_handle: ny2 = oy2_img + dy_img
            if 'w' in self.resize_handle: nx1 = ox1_img + dx_img
            if 'e' in self.resize_handle: nx2 = ox2_img + dx_img

            updated = self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2))

            if updated:
                 validated_img_coords = self.crops[crop_id]['coords']
                 cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                 cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                 self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)


    def on_mouse_release(self, event):
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.is_drawing and self.current_rect_id:
            if self.canvas.find_withtag(self.current_rect_id):
                 self.canvas.delete(self.current_rect_id)

            final_rect_canvas_coords = self.canvas.coords(self.current_rect_id) if self.current_rect_id else (self.start_x, self.start_y, canvas_x, canvas_y)

            img_x1, img_y1 = self.canvas_to_image_coords(final_rect_canvas_coords[0], final_rect_canvas_coords[1])
            img_x2, img_y2 = self.canvas_to_image_coords(final_rect_canvas_coords[2], final_rect_canvas_coords[3])

            if img_x1 is not None and img_y1 is not None and img_x2 is not None and img_y2 is not None:
                 self.add_crop(img_x1, img_y1, img_x2, img_y2)

        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.current_rect_id = None
        self.start_coords_img = None
        self.start_coords_canvas = None

        self.update_cursor(event)

    # --- Zoom and Pan Handlers ---
    def on_mouse_wheel(self, event, direction=None):
        if not self.original_image: return

        if direction:
            delta = direction
        elif event.num == 5 or event.delta < 0:
            delta = -1
        elif event.num == 4 or event.delta > 0:
            delta = 1
        else:
            return

        zoom_increment = 1.1
        min_zoom = 0.01
        max_zoom = 20.0

        canvas_center_x = self.canvas.canvasx(event.x)
        canvas_center_y = self.canvas.canvasy(event.y)

        img_x_before, img_y_before = self.canvas_to_image_coords(canvas_center_x, canvas_center_y)
        if img_x_before is None: return

        new_zoom = self.zoom_factor * zoom_increment if delta > 0 else self.zoom_factor / zoom_increment
        new_zoom = max(min_zoom, min(max_zoom, new_zoom))

        if new_zoom == self.zoom_factor: return

        self.zoom_factor = new_zoom

        self.canvas_offset_x = canvas_center_x - (img_x_before * self.zoom_factor)
        self.canvas_offset_y = canvas_center_y - (img_y_before * self.zoom_factor)

        self.display_image_on_canvas()

    def on_pan_press(self, event):
        if not self.original_image: return
        self.is_panning = True
        self.pan_start_x = self.canvas.canvasx(event.x)
        self.pan_start_y = self.canvas.canvasy(event.y)
        self.canvas.config(cursor="fleur")

    def on_pan_drag(self, event):
        if not self.is_panning or not self.original_image: return
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

    # --- Listbox Event Handlers ---
    def on_listbox_select(self, event=None):
        """Handles selection changes in the listbox."""
        selection = self.crop_listbox.curselection()

        if selection:
             self.btn_delete_crops.configure(state=tk.NORMAL)
        else:
             self.btn_delete_crops.configure(state=tk.DISABLED)

        if len(selection) == 1:
            selected_index = selection[0]
            if selected_index < len(self.crop_order):
                 selected_crop_id = self.crop_order[selected_index]
                 self.select_crop(selected_crop_id, from_listbox=True)
            else:
                 print("Warning: Listbox index out of sync with crop_order.")
                 self.select_crop(None, from_listbox=True)
        else:
            self.select_crop(None, from_listbox=True)

    def on_listbox_double_click(self, event):
        """Handles double-click on a listbox item to rename it."""
        try:
            selected_index = self.crop_listbox.nearest(event.y)
            bbox = self.crop_listbox.bbox(selected_index)
            if not bbox or not (bbox[1] <= event.y <= bbox[1] + bbox[3]):
                return

            if selected_index < len(self.crop_order):
                crop_id = self.crop_order[selected_index]
                current_name = self.crops[crop_id]['name']

                new_name = simpledialog.askstring(
                    "Rename Crop",
                    "Enter new name for this crop:",
                    parent=self,
                    initialvalue=current_name
                )

                if new_name and new_name.strip() and new_name.strip() != current_name:
                    self.crops[crop_id]['name'] = new_name.strip()
                    # Update the specific item in the listbox instead of refreshing all
                    self.crop_listbox.delete(selected_index)
                    self.crop_listbox.insert(selected_index, self.crops[crop_id]['name'])
                    # Restore selection after replacing the item
                    self.crop_listbox.selection_set(selected_index)
                    self.crop_listbox.activate(selected_index)
                    # Note: This manual update doesn't trigger <<ListboxSelect>>.
                    # If needed, manually call self.on_listbox_select()

        except IndexError:
            pass
        except Exception as e:
            print(f"Error during renaming: {e}")

    # --- Listbox Drag and Drop ---
    def on_listbox_press(self, event):
        try:
            pressed_index = self.crop_listbox.nearest(event.y)
            bbox = self.crop_listbox.bbox(pressed_index)
            if not bbox or not (bbox[1] <= event.y <= bbox[1] + bbox[3]):
                 self.reset_listbox_drag_state()
                 return

            if pressed_index < len(self.crop_order):
                self.drag_start_index = pressed_index
                self.drag_item_id = self.crop_order[pressed_index]
                self.is_dragging_listbox = False # Set true in motion
                # self.crop_listbox.config(cursor="fleur") # Optional: change cursor
        except IndexError:
            self.reset_listbox_drag_state()
            pass

    def on_listbox_drag(self, event):
        if self.drag_item_id is None: return

        self.is_dragging_listbox = True # Now definitely dragging

        try:
            # Get the index the mouse is currently over
            current_index = self.crop_listbox.nearest(event.y)
            current_index = max(0, min(current_index, self.crop_listbox.size())) # Clamp

            # Visual feedback: Could potentially highlight the target row index
            # This is hard with standard Listbox without breaking selection visuals.
            # Skipping visual drag feedback during motion for simplicity.

        except IndexError:
            # Mouse outside listbox bounds
            y_pos = event.y
            listbox_height = self.crop_listbox.winfo_height()
            if y_pos < 0: current_index = 0
            elif y_pos > listbox_height: current_index = self.crop_listbox.size()
            else: current_index = None # Mouse is within the listbox widget but somehow nearest failed?

        if current_index is not None and self.drag_start_index is not None and current_index != self.drag_start_index:
             # Move the item temporarily in the listbox for visual feedback
             # This is simpler than drawing lines/ghosts
             item_name = self.crops[self.drag_item_id]['name']
             self.crop_listbox.delete(self.drag_start_index)
             self.crop_listbox.insert(current_index, item_name)

             # Update internal drag start index for the *next* drag event
             # As we moved the item visually, its index is now `current_index`
             self.drag_start_index = current_index

             # Need to update selection as delete/insert clears it
             self.crop_listbox.selection_clear(0, tk.END)
             self.crop_listbox.selection_set(current_index)
             self.crop_listbox.activate(current_index)


    def on_listbox_release(self, event):
        if not self.is_dragging_listbox or self.drag_item_id is None:
            self.reset_listbox_drag_state()
            # If only single item selected on press, ensure it stays selected after release
            if self.drag_start_index is not None and self.drag_start_index < self.crop_listbox.size():
                 self.crop_listbox.selection_clear(0, tk.END)
                 self.crop_listbox.selection_set(self.drag_start_index)
                 self.crop_listbox.activate(self.drag_start_index)
            return

        # If a drag occurred, the visual Listbox is already updated.
        # Need to update the internal crop_order list to match the *final* visual state.

        # Find the final position of the dragged item's ID in the visually reordered listbox
        final_index = -1
        for i in range(self.crop_listbox.size()):
            # Match by crop_id, looking up name from self.crops
            item_name_in_listbox = self.crop_listbox.get(i)
            # Find the crop_id that has this name and matches the dragged_item_id
            found_crop_id = None
            for cid, data in self.crops.items():
                 if data['name'] == item_name_in_listbox and cid == self.drag_item_id:
                      found_crop_id = cid
                      break
            if found_crop_id == self.drag_item_id:
                 final_index = i
                 break # Found the dragged item's final position

        if final_index != -1:
             # Rebuild crop_order based on the final listbox state
             new_crop_order = []
             for i in range(self.crop_listbox.size()):
                 item_name = self.crop_listbox.get(i)
                 # Find the crop_id corresponding to this name.
                 # Need to handle potential duplicate names.
                 # A more robust approach would be to store crop_id in the listbox item itself (e.g., using data attribute, but Listbox is limited)
                 # Or ensure names are unique, or find the *correct* ID based on original state vs dragged ID.
                 # For simplicity, assume names are unique enough for finding the ID here.
                 # Better approach: Use the stored self.crops dict to map names back to IDs.
                 found_id = None
                 for cid, data in self.crops.items():
                      if data['name'] == item_name:
                           # Simple check: if the dragged item's name is duplicated, this could pick the wrong one.
                           # Need a more robust way to map listbox index back to crop_id after visual drag.
                           # The visual drag-and-drop in Listbox is tricky because it doesn't inherently carry data (like crop_id) per row.
                           # The simplest reliable way after a visual drag is to rebuild crop_order by looking up IDs based on names
                           # and assuming names are unique enough for lookup after reordering.

                           # More robust approach: Rebuild crop_order by iterating the *visual* listbox contents
                           # and finding the crop_id that matches the item name *and* isn't already added to the new_crop_order
                           is_already_added = False
                           for existing_id in new_crop_order:
                                if existing_id in self.crops and self.crops[existing_id]['name'] == item_name:
                                     is_already_added = True
                                     break
                           if not is_already_added:
                                found_id = cid
                                break # Found an ID for this name not already added

                 if found_id:
                      new_crop_order.append(found_id)
                 else:
                      print(f"Warning: Could not find unique crop_id for name '{item_name}' during reorder rebuild.")

             if len(new_crop_order) == self.crop_listbox.size(): # Only update if we successfully mapped all items
                  self.crop_order = new_crop_order
                  # Selection is already set by on_listbox_drag or will be set by on_listbox_select
                  # No need to call refresh_listbox here, as the visual listbox is already updated.
                  # Trigger selection logic manually if needed, or rely on the next user click.
                  # self.on_listbox_select() # Can call this to ensure canvas highlights match

        self.reset_listbox_drag_state()
        # self.crop_listbox.config(cursor="") # Optional: reset cursor

    def reset_listbox_drag_state(self):
        self.is_dragging_listbox = False
        self.drag_start_index = None
        self.drag_item_id = None
        # self.crop_listbox.config(cursor="") # Ensure cursor is reset

    # --- Resizing Helpers ---
    def get_resize_handle(self, canvas_x, canvas_y):
        """Checks if the cursor is near a resize handle of the selected crop."""
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            return None

        rect_id = self.crops[self.selected_crop_id]['rect_id']
        if not self.canvas.find_withtag(rect_id):
            return None

        cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
        margin = RESIZE_HANDLE_MARGIN

        dist_w = abs(canvas_x - cx1)
        dist_e = abs(canvas_x - cx2)
        dist_n = abs(canvas_y - cy1)
        dist_s = abs(canvas_y - cy2)

        is_near_h_edge = (cx1 - margin) <= canvas_x <= (cx2 + margin)
        is_near_v_edge = (cy1 - margin) <= canvas_y <= (cy2 + margin)

        handle = ''
        if dist_n < margin and dist_w < margin: handle = 'nw'
        elif dist_n < margin and dist_e < margin: handle = 'ne'
        elif dist_s < margin and dist_w < margin: handle = 'sw'
        elif dist_s < margin and dist_e < margin: handle = 'se'
        elif dist_n < margin and is_near_h_edge: handle = 'n'
        elif dist_s < margin and is_near_h_edge: handle = 's'
        elif dist_w < margin and is_near_v_edge: handle = 'w'
        elif dist_e < margin and is_near_v_edge: handle = 'e'

        expanded_cx1 = cx1 - margin
        expanded_cy1 = cy1 - margin
        expanded_cx2 = cx2 + margin
        expanded_cy2 = cy2 + margin
        if not (expanded_cx1 <= canvas_x <= expanded_cx2 and expanded_cy1 <= canvas_y <= expanded_cy2):
             return None

        return handle if handle else None

    def get_handle_cursor(self, handle):
        """Maps handle names to Tk cursor names."""
        if handle in ('nw', 'se'): return "size_nw_se"
        elif handle in ('ne', 'sw'): return "size_ne_sw"
        elif handle in ('n', 's'): return "size_ns"
        elif handle in ('e', 'w'): return "size_we"
        return ""

    def update_cursor(self, event=None):
        """Changes the mouse cursor based on position."""
        if self.is_panning or self.is_moving or self.is_resizing or self.is_dragging_listbox:
            return

        new_cursor = ""

        if event and self.original_image:
            canvas_x = self.canvas.canvasx(event.x)
            canvas_y = self.canvas.canvasy(event.y)

            if self.selected_crop_id:
                 handle = self.get_resize_handle(canvas_x, canvas_y)
                 if handle:
                      new_cursor = self.get_handle_cursor(handle)
                      self.canvas.config(cursor=new_cursor)
                      return

            if self.selected_crop_id and self.selected_crop_id in self.crops:
                 rect_id = self.crops[self.selected_crop_id]['rect_id']
                 if self.canvas.find_withtag(rect_id):
                      cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
                      buffer = 2
                      if (cx1 + buffer) < canvas_x < (cx2 - buffer) and (cy1 + buffer) < canvas_y < (cy2 - buffer):
                          new_cursor = "fleur"
                          self.canvas.config(cursor=new_cursor)
                          return

        if self.canvas.cget("cursor") != "":
             self.canvas.config(cursor="")

    # --- Window/Canvas Resize Handling ---
    def on_canvas_configure(self, event=None):
         """Handler for when the canvas widget changes size."""
         if self.original_image and self.tk_image:
             canvas_center_x = self.canvas.winfo_width() / 2
             canvas_center_y = self.canvas.winfo_height() / 2
             img_center_x, img_center_y = self.canvas_to_image_coords(self.canvas.canvasx(canvas_center_x), self.canvas.canvasy(canvas_center_y))

             new_canvas_offset_x = self.canvas.winfo_width() / 2 - (img_center_x * self.zoom_factor) if img_center_x is not None else self.canvas_offset_x
             new_canvas_offset_y = self.canvas.winfo_height() / 2 - (img_center_y * self.zoom_factor) if img_center_y is not None else self.canvas_offset_y

             self.canvas_offset_x = new_canvas_offset_x
             self.canvas_offset_y = new_canvas_offset_y

             self.display_image_on_canvas()

         elif not self.original_image and self.canvas.find_all():
             self.canvas.delete("all")

    # --- Saving Crops ---
    def save_crops(self):
        if not self.original_image or not self.image_path:
            messagebox.showwarning("No Image", "Please select an image first.")
            return
        if not self.crops:
            messagebox.showwarning("No Crops", "Please define at least one crop area.")
            return

        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        output_dir = os.path.join(script_dir, base_name)

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Directory Error", f"Could not create output directory:\n{output_dir}\n{e}")
            return

        saved_count = 0
        error_count = 0

        # Iterate through crops using the user-defined order (self.crop_order)
        for i, crop_id in enumerate(self.crop_order, start=1):
            if crop_id in self.crops:
                data = self.crops[crop_id]
                coords = tuple(map(int, data['coords']))

                filename = f"{base_name}_{i}.jpg"
                filepath = os.path.join(output_dir, filename)

                try:
                    img_w, img_h = self.original_image.size
                    valid_coords = (
                        max(0, coords[0]), max(0, coords[1]),
                        min(img_w, coords[2]), min(img_h, coords[3])
                    )
                    if valid_coords[2] > valid_coords[0] and valid_coords[3] > valid_coords[1]:
                        cropped_img = self.original_image.crop(valid_coords)
                        if cropped_img.mode in ('RGBA', 'P'):
                            cropped_img = cropped_img.convert('RGB')
                        cropped_img.save(filepath, "JPEG", quality=95)
                        saved_count += 1
                    else:
                         error_count += 1
                         print(f"Error saving {filename}: Invalid crop dimensions {valid_coords}")

                except Exception as e:
                    error_count += 1
                    print(f"Error saving {filename}: {e}")

            else:
                print(f"Warning: crop_id {crop_id} found in crop_order but not in crops dictionary during save!")
                error_count += 1

        if saved_count > 0 or error_count > 0:
            if error_count == 0:
                messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to the '{base_name}' folder.")
            else:
                messagebox.showwarning("Partial Success", f"Saved {saved_count} crops to '{base_name}'.\nFailed to save {error_count} crops. Check console/log for details.")
        else:
            messagebox.showinfo("No Crops Saved", "No valid crops were saved.")


# --- Run the Application ---
if __name__ == "__main__":
    app = MultiCropApp()
    app.mainloop()
