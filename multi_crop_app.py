import tkinter as tk
from tkinter import filedialog, messagebox, Listbox, simpledialog
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid
import math

# --- Constants ---
RECT_TAG_PREFIX = "crop_rect_"
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
MIN_CROP_SIZE = 10
# Output folder generated dynamically

# --- Main Application Class ---
class MultiCropApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Multi Image Cropper (Right-Click Select)")
        self.geometry("1150x750")
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        # --- State Variables ---
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.tk_image = None
        self.canvas_image_id = None

        # Crop Data Management
        self.crops = {}
        self.crop_order = []
        self.used_crop_numbers = set()
        self.selected_crop_ids = []

        # Drawing/Editing State
        self.start_x = None
        self.start_y = None
        self.current_rect_id = None # Temporary rect for drawing
        self.is_drawing = False
        self.is_moving = False      # Flag to indicate if a move operation is active
        self._potential_move_id = None # ID of the crop clicked on, potential move target
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

        # --- UI Layout ---
        self.grid_columnconfigure(0, weight=3) # Image area
        self.grid_columnconfigure(1, weight=1) # Control panel
        self.grid_rowconfigure(0, weight=1)

        # --- Left Frame (Image Display) ---
        self.image_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)

        # Canvas
        self.canvas = tk.Canvas(self.image_frame, bg="gray90", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # --- Right Frame (Controls) ---
        self.control_frame = ctk.CTkFrame(self, width=300) # Wider for buttons
        self.control_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False)
        self.control_frame.grid_rowconfigure(4, weight=1) # Listbox frame row
        self.control_frame.grid_columnconfigure(0, weight=1) # Main column
        self.control_frame.grid_columnconfigure(1, weight=0) # Move buttons column

        # Buttons (Main)
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image", command=self.select_image)
        self.btn_select_image.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew")

        self.btn_save_crops = ctk.CTkButton(self.control_frame, text="Save All Crops", command=self.save_crops, state=tk.DISABLED)
        self.btn_save_crops.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

        # Crop List Label
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List (Double-Click to Rename):")
        self.lbl_crop_list.grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w")

        # Listbox Frame
        self.listbox_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.listbox_frame.grid(row=3, column=0, padx=(10,0), pady=5, sticky="nsew")
        self.listbox_frame.grid_rowconfigure(0, weight=1)
        self.listbox_frame.grid_columnconfigure(0, weight=1)

        # Listbox Scrollbar
        self.listbox_scrollbar = ctk.CTkScrollbar(self.listbox_frame, command=None)
        self.listbox_scrollbar.grid(row=0, column=1, sticky="ns")

        # Crop Listbox
        self.crop_listbox = Listbox(self.listbox_frame,
                                    bg='white', fg='black',
                                    selectbackground='#ADD8E6', selectforeground='black',
                                    highlightthickness=1, highlightbackground="#CCCCCC",
                                    highlightcolor="#89C4F4", borderwidth=0, exportselection=False,
                                    selectmode=tk.EXTENDED, yscrollcommand=self.listbox_scrollbar.set)
        self.crop_listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox_scrollbar.configure(command=self.crop_listbox.yview)

        # Move Buttons Frame
        self.move_button_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.move_button_frame.grid(row=3, column=1, padx=(5, 10), pady=5, sticky="ns")

        self.btn_move_up = ctk.CTkButton(self.move_button_frame, text="↑", width=30, command=self.move_selected_item_up, state=tk.DISABLED)
        self.btn_move_up.pack(pady=(0, 5), padx=0)

        self.btn_move_down = ctk.CTkButton(self.move_button_frame, text="↓", width=30, command=self.move_selected_item_down, state=tk.DISABLED)
        self.btn_move_down.pack(pady=(5, 0), padx=0)

        # Delete Button
        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete Selected Crop(s)", command=self.delete_selected_crops, state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crop.grid(row=4, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="sew")

        # --- Bindings ---
        # Canvas Bindings (Simplified Click, Added Right-Click)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_left_press) # Renamed for clarity
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)          # Renamed for clarity
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_left_release) # Renamed for clarity
        self.canvas.bind("<Button-3>", self.on_canvas_right_click)      # *** ADDED Right-click ***
        # Optional: Add binding for macOS right-click if Button-3 doesn't work reliably
        # self.canvas.bind("<Button-2>", self.on_canvas_right_click) # Or <Control-Button-1>

        # Other Canvas Bindings
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1))
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1))
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press) # Keep middle button for panning
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.update_cursor)

        # Listbox Bindings
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.crop_listbox.bind("<Double-Button-1>", self.on_listbox_double_click) # Rename

        # Global Key Bindings
        self.bind("<Delete>", self.delete_selected_crops_event)
        self.bind("<BackSpace>", self.delete_selected_crops_event)
        self.bind("<Configure>", self.on_window_resize)

    # --- Image Handling (Unchanged from previous version) ---
    def select_image(self):
        path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff")]
        )
        if not path: return
        try:
            self.image_path = path
            self.original_image = Image.open(self.image_path)
            self.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            if canvas_width <= 1 or canvas_height <= 1: canvas_width, canvas_height = 600, 500
            img_width, img_height = self.original_image.size
            if img_width <= 0 or img_height <= 0: raise ValueError("Image has zero or negative dimension")
            zoom_h = canvas_width / img_width; zoom_v = canvas_height / img_height
            initial_zoom = min(zoom_h, zoom_v); padding_factor = 0.98
            self.zoom_factor = min(1.0, initial_zoom) * padding_factor
            display_w = img_width * self.zoom_factor; display_h = img_height * self.zoom_factor
            self.canvas_offset_x = math.ceil((canvas_width - display_w) / 2)
            self.canvas_offset_y = math.ceil((canvas_height - display_h) / 2)
            self.clear_all_crops()
            self.display_image_on_canvas()
            self.update_button_states()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or process image:\n{e}")
            self.image_path = None; self.original_image = None
            self.clear_all_crops(); self.canvas.delete("all")
            self.tk_image = None; self.display_image = None
            self.update_button_states()

    def clear_all_crops(self):
        self.canvas.delete("crop_rect")
        self.crops.clear(); self.crop_order = []
        self.used_crop_numbers = set(); self.selected_crop_ids = []
        self.crop_listbox.delete(0, tk.END)
        self.update_button_states()

    def display_image_on_canvas(self):
        if not self.original_image: self.canvas.delete("all"); return
        disp_w = max(1, int(self.original_image.width * self.zoom_factor))
        disp_h = max(1, int(self.original_image.height * self.zoom_factor))
        try:
            self.display_image = self.original_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        except Exception as e:
             print(f"Error resizing image: {e}"); self.display_image = None; self.canvas.delete("all"); return
        self.tk_image = ImageTk.PhotoImage(self.display_image)
        self.canvas.delete("all")
        int_offset_x = int(round(self.canvas_offset_x)); int_offset_y = int(round(self.canvas_offset_y))
        self.canvas_image_id = self.canvas.create_image(
            int_offset_x, int_offset_y, anchor=tk.NW, image=self.tk_image, tags="image"
        )
        self.redraw_all_crops()

    # --- Coordinate Conversion (Unchanged) ---
    def canvas_to_image_coords(self, canvas_x, canvas_y):
        if not self.original_image or self.zoom_factor == 0: return None, None
        img_x = (canvas_x - self.canvas_offset_x) / self.zoom_factor
        img_y = (canvas_y - self.canvas_offset_y) / self.zoom_factor
        return img_x, img_y

    def image_to_canvas_coords(self, img_x, img_y):
        if not self.original_image: return None, None
        canvas_x = (img_x * self.zoom_factor) + self.canvas_offset_x
        canvas_y = (img_y * self.zoom_factor) + self.canvas_offset_y
        return canvas_x, canvas_y

    # --- Crop Handling (Minor changes for clarity, logic mostly same) ---
    def find_available_crop_number(self):
        i = 1
        while i in self.used_crop_numbers: i += 1
        return i

    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        if not self.original_image: return
        img_w, img_h = self.original_image.size
        x1_img = max(0, min(x1_img, img_w)); y1_img = max(0, min(y1_img, img_h))
        x2_img = max(0, min(x2_img, img_w)); y2_img = max(0, min(y2_img, img_h))
        if abs(x2_img - x1_img) < MIN_CROP_SIZE or abs(y2_img - y1_img) < MIN_CROP_SIZE:
            print("Crop too small, ignoring.")
            if self.current_rect_id and self.current_rect_id in self.canvas.find_all():
                 self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None; return
        coords = (min(x1_img, x2_img), min(y1_img, y2_img), max(x1_img, x2_img), max(y1_img, y2_img))
        crop_id = str(uuid.uuid4())
        crop_number = self.find_available_crop_number()
        self.used_crop_numbers.add(crop_number)
        base_name = os.path.splitext(os.path.basename(self.image_path))[0] if self.image_path else "Image"
        crop_name = f"{base_name}_Crop_{crop_number}"
        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])
        if cx1 is None: print("Error: Cannot draw crop, coord conversion failed."); self.used_crop_numbers.discard(crop_number); return
        rect_id = self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH, tags=(RECT_TAG_PREFIX + crop_id, "crop_rect"))
        self.crops[crop_id] = {'coords': coords, 'name': crop_name, 'rect_id': rect_id}
        self.crop_order.append(crop_id)
        self.rebuild_listbox()
        new_index = self.get_list_index_from_crop_id(crop_id)
        if new_index != -1:
            # Select the newly added crop
            self.select_crops([crop_id], source="add_crop") # Select only the new one
        self.update_button_states()

    def get_crop_id_from_list_index(self, index):
        if 0 <= index < len(self.crop_order): return self.crop_order[index]
        return None

    def get_list_index_from_crop_id(self, crop_id):
        try: return self.crop_order.index(crop_id)
        except ValueError: return -1

    def select_crops(self, crop_ids_to_select, source="unknown"):
        new_selection = list(crop_ids_to_select)
        if set(self.selected_crop_ids) == set(new_selection): return # No change

        ids_to_deselect = set(self.selected_crop_ids) - set(new_selection)
        for prev_id in ids_to_deselect:
            if prev_id in self.crops:
                rect_id = self.crops[prev_id].get('rect_id')
                if rect_id and rect_id in self.canvas.find_all():
                     try: self.canvas.itemconfig(rect_id, outline=DEFAULT_RECT_COLOR)
                     except tk.TclError as e: print(f"Warning: TclError deselecting {rect_id}: {e}")

        self.selected_crop_ids = new_selection

        for crop_id in self.selected_crop_ids:
            if crop_id in self.crops:
                rect_id = self.crops[crop_id].get('rect_id')
                if rect_id and rect_id in self.canvas.find_all():
                    try:
                        self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR)
                        self.canvas.tag_raise(rect_id)
                    except tk.TclError as e: print(f"Warning: TclError selecting/raising {rect_id}: {e}")
                elif rect_id: print(f"Warning: Stale rectangle ID {rect_id} for crop {crop_id}")
            else: print(f"Warning: Attempted to select non-existent crop ID {crop_id}")

        self.update_button_states()
        if source != "listbox":
            self.update_listbox_selection_visuals()

    def update_crop_coords(self, crop_id, new_img_coords):
        # (Unchanged - same validation logic)
        if crop_id in self.crops and self.original_image:
             img_w, img_h = self.original_image.size
             x1, y1, x2, y2 = new_img_coords
             x1=max(0, min(x1, img_w)); y1=max(0, min(y1, img_h)); x2=max(0, min(x2, img_w)); y2=max(0, min(y2, img_h))
             final_x1=min(x1,x2); final_y1=min(y1,y2); final_x2=max(x1,x2); final_y2=max(y1,y2)
             if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE: return False
             self.crops[crop_id]['coords'] = (final_x1, final_y1, final_x2, final_y2); return True
        return False

    def redraw_all_crops(self):
        # (Unchanged - redraws based on self.crops and self.selected_crop_ids)
        all_canvas_items_ids = set(self.canvas.find_all())
        for crop_id in self.crop_order:
            if crop_id not in self.crops: continue
            data = self.crops[crop_id]; img_x1, img_y1, img_x2, img_y2 = data['coords']
            cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1); cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)
            if cx1 is None: continue
            color = SELECTED_RECT_COLOR if crop_id in self.selected_crop_ids else DEFAULT_RECT_COLOR
            tags_tuple = (RECT_TAG_PREFIX + crop_id, "crop_rect"); rect_id = data.get('rect_id')
            try:
                if rect_id and rect_id in all_canvas_items_ids:
                    self.canvas.coords(rect_id, cx1, cy1, cx2, cy2); self.canvas.itemconfig(rect_id, outline=color, tags=tags_tuple)
                else:
                    new_rect_id = self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=color, width=RECT_WIDTH, tags=tags_tuple)
                    self.crops[crop_id]['rect_id'] = new_rect_id; rect_id = new_rect_id
                if crop_id in self.selected_crop_ids and rect_id: self.canvas.tag_raise(rect_id)
            except tk.TclError as e: print(f"Error drawing/updating rect for {crop_id} (ID: {rect_id}): {e}")

    def delete_selected_crops_event(self, event=None):
        self.delete_selected_crops()

    def delete_selected_crops(self):
        # (Unchanged - deletes based on self.selected_crop_ids)
        ids_to_delete = list(self.selected_crop_ids)
        if not ids_to_delete:
            indices_to_delete = self.crop_listbox.curselection()
            if not indices_to_delete: return
            ids_to_delete = [self.get_crop_id_from_list_index(i) for i in indices_to_delete]; ids_to_delete = [id for id in ids_to_delete if id]
        if not ids_to_delete: return
        deleted_count = 0
        for crop_id in ids_to_delete:
            if crop_id in self.crops:
                data = self.crops[crop_id]
                try:
                    parts=data['name'].split('_'); num = int(parts[-1]) if len(parts)>1 and parts[-1].isdigit() else None
                    if num: self.used_crop_numbers.discard(num)
                except: pass
                rect_id = data.get('rect_id')
                if rect_id and rect_id in self.canvas.find_all():
                    try: self.canvas.delete(rect_id)
                    except tk.TclError as e: print(f"Warning: TclError deleting rect {rect_id}: {e}")
                del self.crops[crop_id]; deleted_count += 1
        self.crop_order = [id for id in self.crop_order if id not in ids_to_delete]
        self.selected_crop_ids = []; self.rebuild_listbox(); print(f"Deleted {deleted_count} crop(s)."); self.update_button_states()

    def rebuild_listbox(self):
        # (Unchanged)
        self.crop_listbox.delete(0, tk.END)
        for crop_id in self.crop_order:
            if crop_id in self.crops: self.crop_listbox.insert(tk.END, self.crops[crop_id]['name'])
            else: print(f"Warning: crop_id {crop_id} in order but not in crops dict.")

    def update_button_states(self):
        # (Unchanged - includes move button logic)
        has_crops = bool(self.crops); num_selected = len(self.selected_crop_ids)
        listbox_selection_indices = self.crop_listbox.curselection(); listbox_num_selected = len(listbox_selection_indices)
        self.btn_save_crops.configure(state=tk.NORMAL if has_crops else tk.DISABLED)
        self.btn_delete_crop.configure(state=tk.NORMAL if num_selected > 0 else tk.DISABLED)
        can_move_up = False; can_move_down = False
        if listbox_num_selected == 1:
            idx = listbox_selection_indices[0]
            if idx > 0: can_move_up = True
            if idx < self.crop_listbox.size() - 1: can_move_down = True
        self.btn_move_up.configure(state=tk.NORMAL if can_move_up else tk.DISABLED)
        self.btn_move_down.configure(state=tk.NORMAL if can_move_down else tk.DISABLED)

    # --- Mouse Event Handlers (Canvas - Reworked) ---

    def on_canvas_left_press(self, event):
        """ Handles Button-1 press: Select, start draw, move, or resize. """
        self.canvas.focus_set()
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.start_x, self.start_y = canvas_x, canvas_y
        self._potential_move_id = None # Reset potential move target

        # 1. Check for Resize Handle (only if exactly one crop selected)
        handle = None
        clicked_crop_id = None
        item_id = self.find_topmost_crop_rect(canvas_x, canvas_y) # Find item under cursor

        if item_id:
             tags = self.canvas.gettags(item_id)
             if tags and tags[0].startswith(RECT_TAG_PREFIX):
                  clicked_crop_id = tags[0][len(RECT_TAG_PREFIX):]

        if len(self.selected_crop_ids) == 1 and clicked_crop_id == self.selected_crop_ids[0]:
             handle = self.get_resize_handle(canvas_x, canvas_y, clicked_crop_id)

        if handle:
            self.is_resizing = True
            self.resize_handle = handle
            self.start_coords_img = self.crops[clicked_crop_id]['coords']
            # print(f"Starting resize on {clicked_crop_id}")
            return # Don't proceed further

        # 2. Check if clicking inside any existing rectangle
        if clicked_crop_id:
            # If the clicked crop is NOT currently selected, select ONLY it.
            if clicked_crop_id not in self.selected_crop_ids:
                # print(f"Left-click selecting {clicked_crop_id}")
                self.select_crops([clicked_crop_id], source="left_click_select")

            # Prepare for potential move (will activate on drag)
            # print(f"Potential move target: {clicked_crop_id}")
            self._potential_move_id = clicked_crop_id
            rect_id = self.crops[clicked_crop_id].get('rect_id')
            if rect_id:
                try:
                    rect_coords = self.canvas.coords(rect_id)
                    self.move_offset_x = canvas_x - rect_coords[0]
                    self.move_offset_y = canvas_y - rect_coords[1]
                except tk.TclError:
                    print("Error getting coords for potential move.")
            return # Don't start drawing

        # 3. Clicked on empty space: Prepare for drawing & deselect all
        # print("Left-click on empty space, preparing to draw and deselecting.")
        self.is_drawing = True
        self.current_rect_id = None # Will be created on drag
        if self.selected_crop_ids: # Deselect if anything was selected
            self.select_crops([], source="left_click_deselect")


    def on_canvas_drag(self, event):
        """ Handles motion with Button-1 held down. """
        if self.is_panning: return # Ignore if panning with middle button

        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # --- Resize ---
        if self.is_resizing and len(self.selected_crop_ids) == 1 and self.resize_handle:
            # (Resize logic is unchanged)
            crop_id = self.selected_crop_ids[0]
            if not crop_id in self.crops: return
            rect_id = self.crops[crop_id]['rect_id']
            ox1_img, oy1_img, ox2_img, oy2_img = self.start_coords_img
            curr_img_x, curr_img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            if curr_img_x is None: return
            nx1, ny1, nx2, ny2 = ox1_img, oy1_img, ox2_img, oy2_img
            if 'n' in self.resize_handle: ny1 = curr_img_y
            if 's' in self.resize_handle: ny2 = curr_img_y
            if 'w' in self.resize_handle: nx1 = curr_img_x
            if 'e' in self.resize_handle: nx2 = curr_img_x
            updated = self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2))
            if updated:
                 v_coords = self.crops[crop_id]['coords']
                 cx1_f, cy1_f = self.image_to_canvas_coords(v_coords[0], v_coords[1])
                 cx2_f, cy2_f = self.image_to_canvas_coords(v_coords[2], v_coords[3])
                 if cx1_f is not None:
                     try: self.canvas.coords(rect_id, cx1_f, cy1_f, cx2_f, cy2_f)
                     except tk.TclError as e: print(f"Error updating coords during resize: {e}")
            return # Don't check move/draw if resizing

        # --- Move ---
        # Activate move only if dragging started on a selected item
        if self._potential_move_id and self._potential_move_id in self.selected_crop_ids and not self.is_moving:
             # Check sufficient drag distance to differentiate from click
             if math.hypot(canvas_x - self.start_x, canvas_y - self.start_y) > 3:
                  # Only allow moving if exactly ONE item is selected
                  if len(self.selected_crop_ids) == 1:
                       self.is_moving = True
                       # print(f"Move activated for {self._potential_move_id}")
                  else:
                       # print("Cannot move multiple items yet.")
                       self._potential_move_id = None # Prevent move if multi-selected

        if self.is_moving and len(self.selected_crop_ids) == 1:
            # (Move logic is unchanged - operates on the single selected item)
            crop_id = self.selected_crop_ids[0]
            if not crop_id in self.crops: return
            rect_id = self.crops[crop_id]['rect_id']
            try:
                current_canvas_coords = self.canvas.coords(rect_id)
                w = current_canvas_coords[2] - current_canvas_coords[0]
                h = current_canvas_coords[3] - current_canvas_coords[1]
                new_cx1 = canvas_x - self.move_offset_x; new_cy1 = canvas_y - self.move_offset_y
                new_cx2 = new_cx1 + w; new_cy2 = new_cy1 + h
                img_x1, img_y1 = self.canvas_to_image_coords(new_cx1, new_cy1)
                img_x2, img_y2 = self.canvas_to_image_coords(new_cx2, new_cy2)
                if img_x1 is not None:
                    updated = self.update_crop_coords(crop_id, (img_x1, img_y1, img_x2, img_y2))
                    if updated:
                        v_coords = self.crops[crop_id]['coords']
                        cx1_f, cy1_f = self.image_to_canvas_coords(v_coords[0], v_coords[1])
                        cx2_f, cy2_f = self.image_to_canvas_coords(v_coords[2], v_coords[3])
                        if cx1_f is not None: self.canvas.coords(rect_id, cx1_f, cy1_f, cx2_f, cy2_f)
            except tk.TclError as e: print(f"Error during move operation: {e}"); self.is_moving=False # Stop move on error
            return # Don't check draw if moving

        # --- Draw ---
        if self.is_drawing:
            # Create rectangle on first drag after press
            if not self.current_rect_id:
                # Ensure we actually moved a bit before creating
                if math.hypot(canvas_x - self.start_x, canvas_y - self.start_y) > 1:
                    self.current_rect_id = self.canvas.create_rectangle(
                        self.start_x, self.start_y, canvas_x, canvas_y,
                        outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4),
                        tags=("temp_rect",)
                    )
            elif self.current_rect_id in self.canvas.find_all(): # Update existing temp rect
                try:
                    self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)
                except tk.TclError as e: print(f"Error updating draw rect coords: {e}")


    def on_canvas_left_release(self, event):
        """ Handles Button-1 release: Finalize draw, reset states. """
        # Finalize drawing if one was in progress
        if self.is_drawing and self.current_rect_id:
            if self.current_rect_id in self.canvas.find_all():
                try:
                    # Get final coords before deleting
                    final_coords = self.canvas.coords(self.current_rect_id)
                    self.canvas.delete(self.current_rect_id)
                    # Convert end coords to image coords
                    end_x, end_y = final_coords[2], final_coords[3]
                    img_x1, img_y1 = self.canvas_to_image_coords(self.start_x, self.start_y)
                    img_x2, img_y2 = self.canvas_to_image_coords(end_x, end_y)
                    if img_x1 is not None and img_x2 is not None:
                         self.add_crop(img_x1, img_y1, img_x2, img_y2)
                    else: print("Failed to add crop due to coord conversion error.")
                except tk.TclError as e: print(f"Error finalizing draw: {e}")
            else: print("Draw rect disappeared before release?")

        # Reset flags
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.current_rect_id = None
        self._potential_move_id = None
        self.update_cursor(event)


    def on_canvas_right_click(self, event):
        """ Handles Button-3 press: Selects the crop under the cursor exclusively. """
        self.canvas.focus_set()
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        # print(f"Right click at {canvas_x}, {canvas_y}") # Debug

        item_id = self.find_topmost_crop_rect(canvas_x, canvas_y)
        if item_id:
            tags = self.canvas.gettags(item_id)
            clicked_crop_id = None
            if tags and tags[0].startswith(RECT_TAG_PREFIX):
                 clicked_crop_id = tags[0][len(RECT_TAG_PREFIX):]

            if clicked_crop_id and clicked_crop_id in self.crops:
                # Select only this crop
                # print(f"Right-click selecting {clicked_crop_id}")
                self.select_crops([clicked_crop_id], source="right_click")
            # else: Found item but not a valid crop? Do nothing.
        # else: Right-clicked on empty space. Do nothing.

    def find_topmost_crop_rect(self, canvas_x, canvas_y):
        # (Unchanged)
        try:
            overlapping_ids = self.canvas.find_overlapping(canvas_x - 1, canvas_y - 1, canvas_x + 1, canvas_y + 1)
            for item_id in reversed(overlapping_ids):
                tags = self.canvas.gettags(item_id)
                if "crop_rect" in tags: return item_id
        except tk.TclError as e: print(f"Error finding overlapping items: {e}")
        return None

    # --- Zoom and Pan Handlers (Unchanged) ---
    def on_mouse_wheel(self, event, direction=None):
        # (Code unchanged)
        if not self.original_image: return
        delta = 0
        if direction: delta = direction
        elif hasattr(event, 'delta') and event.delta != 0 : delta = event.delta // abs(event.delta)
        elif event.num == 5: delta = -1; elif event.num == 4: delta = 1
        else: return
        zoom_increment = 1.1; min_zoom, max_zoom = 0.01, 20.0
        canvas_x = self.canvas.canvasx(event.x); canvas_y = self.canvas.canvasy(event.y)
        img_x_before, img_y_before = self.canvas_to_image_coords(canvas_x, canvas_y)
        if img_x_before is None: return
        if delta > 0: new_zoom = self.zoom_factor * zoom_increment
        else: new_zoom = self.zoom_factor / zoom_increment
        new_zoom = max(min_zoom, min(max_zoom, new_zoom))
        if new_zoom == self.zoom_factor: return
        self.zoom_factor = new_zoom
        self.canvas_offset_x = canvas_x - (img_x_before * self.zoom_factor)
        self.canvas_offset_y = canvas_y - (img_y_before * self.zoom_factor)
        self.display_image_on_canvas()

    def on_pan_press(self, event):
        # (Code unchanged)
        if not self.original_image or self.is_drawing or self.is_resizing or self.is_moving: return
        self.is_panning = True; self.pan_start_x = self.canvas.canvasx(event.x)
        self.pan_start_y = self.canvas.canvasy(event.y); self.canvas.config(cursor="fleur")

    def on_pan_drag(self, event):
        # (Code unchanged)
        if not self.is_panning or not self.original_image: return
        current_x = self.canvas.canvasx(event.x); current_y = self.canvas.canvasy(event.y)
        dx = current_x - self.pan_start_x; dy = current_y - self.pan_start_y
        self.canvas_offset_x += dx; self.canvas_offset_y += dy
        try: self.canvas.move("all", dx, dy)
        except tk.TclError as e: print(f"Error panning canvas items: {e}")
        self.pan_start_x = current_x; self.pan_start_y = current_y

    def on_pan_release(self, event):
        # (Code unchanged)
        if self.is_panning: self.is_panning = False; self.update_cursor(event)

    # --- Listbox Event Handlers (Unchanged) ---
    def on_listbox_select(self, event=None):
        # (Code unchanged)
        selected_indices = self.crop_listbox.curselection()
        selected_ids_from_list = [self.get_crop_id_from_list_index(i) for i in selected_indices]
        selected_ids_from_list = [id for id in selected_ids_from_list if id and id in self.crops]
        if set(self.selected_crop_ids) != set(selected_ids_from_list):
            self.select_crops(selected_ids_from_list, source="listbox")
        else: self.update_button_states() # Update buttons even if selection IDs didn't change

    def update_listbox_selection_visuals(self):
        # (Code unchanged)
        original_binding = self.crop_listbox.bind("<<ListboxSelect>>"); self.crop_listbox.unbind("<<ListboxSelect>>")
        self.crop_listbox.selection_clear(0, tk.END); indices_to_select = []
        for crop_id in self.selected_crop_ids:
            index = self.get_list_index_from_crop_id(crop_id)
            if index != -1: indices_to_select.append(index)
        if indices_to_select:
             first_index = indices_to_select[0]
             for index in indices_to_select: self.crop_listbox.selection_set(index)
             self.crop_listbox.activate(first_index); self.crop_listbox.see(first_index)
        if original_binding: self.crop_listbox.bind("<<ListboxSelect>>", original_binding)
        else: self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.update_button_states()

    def on_listbox_double_click(self, event):
        # (Code unchanged)
        selected_indices = self.crop_listbox.curselection()
        if len(selected_indices) == 1:
            index = selected_indices[0]; crop_id = self.get_crop_id_from_list_index(index)
            if crop_id and crop_id in self.crops: self.prompt_rename_crop(crop_id, index)

    def prompt_rename_crop(self, crop_id, list_index):
        # (Code unchanged)
        current_name = self.crops[crop_id]['name']
        new_name = simpledialog.askstring("Rename Crop", f"Enter new name for '{current_name}':", initialvalue=current_name, parent=self)
        if new_name and new_name.strip() and new_name != current_name:
            for other_id, data in self.crops.items():
                 if other_id != crop_id and data['name'] == new_name:
                     messagebox.showwarning("Rename Failed", f"Name '{new_name}' already exists.", parent=self); return
            print(f"Renaming crop {crop_id} from '{current_name}' to '{new_name}'")
            self.crops[crop_id]['name'] = new_name; self.rebuild_listbox()
            new_idx = self.get_list_index_from_crop_id(crop_id) # Find index again after rebuild
            if new_idx != -1:
                 self.crop_listbox.selection_set(new_idx)
                 self.update_listbox_selection_visuals() # Sync everything

    # --- Listbox Move Button Actions (Unchanged) ---
    def move_selected_item_up(self):
        # (Code unchanged)
        selection = self.crop_listbox.curselection();
        if len(selection)!=1: return; index=selection[0];
        if index==0: return; crop_id=self.get_crop_id_from_list_index(index);
        if not crop_id: return; self.crop_order.pop(index); self.crop_order.insert(index-1, crop_id)
        self.rebuild_listbox(); self.crop_listbox.selection_set(index-1); self.update_listbox_selection_visuals()

    def move_selected_item_down(self):
        # (Code unchanged)
        selection=self.crop_listbox.curselection();
        if len(selection)!=1: return; index=selection[0];
        if index >= self.crop_listbox.size()-1: return; crop_id=self.get_crop_id_from_list_index(index);
        if not crop_id: return; self.crop_order.pop(index); self.crop_order.insert(index+1, crop_id)
        self.rebuild_listbox(); self.crop_listbox.selection_set(index+1); self.update_listbox_selection_visuals()

    # --- Resizing Helpers (Unchanged) ---
    def get_resize_handle(self, canvas_x, canvas_y, crop_id):
        # (Code unchanged)
        if not crop_id or crop_id not in self.crops: return None
        rect_id = self.crops[crop_id].get('rect_id')
        if not rect_id or rect_id not in self.canvas.find_all(): return None
        try: cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
        except tk.TclError: return None
        m=6; ib=m/2
        if abs(canvas_x-cx1)<m and abs(canvas_y-cy1)<m: return 'nw'
        if abs(canvas_x-cx2)<m and abs(canvas_y-cy1)<m: return 'ne'
        if abs(canvas_x-cx1)<m and abs(canvas_y-cy2)<m: return 'sw'
        if abs(canvas_x-cx2)<m and abs(canvas_y-cy2)<m: return 'se'
        if abs(canvas_y-cy1)<m and (cx1+ib)<canvas_x<(cx2-ib): return 'n'
        if abs(canvas_y-cy2)<m and (cx1+ib)<canvas_x<(cx2-ib): return 's'
        if abs(canvas_x-cx1)<m and (cy1+ib)<canvas_y<(cy2-ib): return 'w'
        if abs(canvas_x-cx2)<m and (cy1+ib)<canvas_y<(cy2-ib): return 'e'
        return None

    def update_cursor(self, event=None):
        # (Code unchanged - cursor logic remains the same based on states)
        new_cursor = ""
        if self.is_panning or self.is_moving: new_cursor = "fleur"
        elif self.is_resizing:
            h = self.resize_handle
            if h in ('nw','se'): new_cursor="size_nw_se"
            elif h in ('ne','sw'): new_cursor="size_ne_sw"
            elif h in ('n','s'): new_cursor="size_ns"
            elif h in ('e','w'): new_cursor="size_we"
        elif self.is_drawing: new_cursor = "crosshair"
        else:
            if event:
                cx=self.canvas.canvasx(event.x); cy=self.canvas.canvasy(event.y)
                handle=None; hover_move=False
                if len(self.selected_crop_ids)==1:
                    sel_id=self.selected_crop_ids[0]; handle=self.get_resize_handle(cx,cy,sel_id)
                    if not handle:
                        item_id=self.find_topmost_crop_rect(cx,cy)
                        if item_id:
                            tags=self.canvas.gettags(item_id); hover_id=None
                            if tags and tags[0].startswith(RECT_TAG_PREFIX): hover_id=tags[0][len(RECT_TAG_PREFIX):]
                            if hover_id==sel_id: hover_move=True
                if handle:
                    if handle in ('nw','se'): new_cursor="size_nw_se"
                    elif handle in ('ne','sw'): new_cursor="size_ne_sw"
                    elif handle in ('n','s'): new_cursor="size_ns"
                    elif handle in ('e','w'): new_cursor="size_we"
                elif hover_move: new_cursor="fleur"
        try:
            if self.canvas.cget("cursor") != new_cursor: self.canvas.config(cursor=new_cursor)
        except tk.TclError as e: print(f"Error setting cursor: {e}")

    # --- Window Resize Handling (Unchanged) ---
    def on_window_resize(self, event=None): pass

    # --- Saving Crops (Unchanged) ---
    def save_crops(self):
        # (Code unchanged - saves based on self.crop_order)
        if not self.original_image or not self.image_path: messagebox.showwarning("No Image", "Please select an image first."); return
        if not self.crops: messagebox.showwarning("No Crops", "Please define at least one crop area."); return
        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        output_dir_base = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
        output_dir = os.path.join(output_dir_base, base_name)
        try: os.makedirs(output_dir, exist_ok=True)
        except OSError as e: messagebox.showerror("Directory Error", f"Could not create output directory:\n{output_dir}\nError: {e}"); return
        saved_count = 0; error_count = 0
        for i, crop_id in enumerate(self.crop_order):
            if crop_id not in self.crops: print(f"Warning: Skipping unknown crop ID {crop_id}"); error_count += 1; continue
            data = self.crops[crop_id]; coords = tuple(map(int, data['coords']))
            filename = f"{base_name}_{i + 1}.jpg"; filepath = os.path.join(output_dir, filename)
            try:
                cropped_img = self.original_image.crop(coords)
                if cropped_img.mode=='RGBA': bg=Image.new('RGB',cropped_img.size,(255,255,255)); bg.paste(cropped_img,(0,0),cropped_img); cropped_img=bg
                elif cropped_img.mode=='P': cropped_img=cropped_img.convert('RGB')
                cropped_img.save(filepath, "JPEG", quality=95); saved_count += 1
            except Exception as e: error_count += 1; print(f"Error saving {filename} (Crop ID: {crop_id}): {e}")
        if error_count == 0: messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to '{os.path.basename(output_dir)}' folder.")
        else: messagebox.showwarning("Partial Success", f"Saved {saved_count} crops to '{os.path.basename(output_dir)}'.\nFailed {error_count} crops. See console.")

# --- Run the Application ---
if __name__ == "__main__":
    app = MultiCropApp()
    app.mainloop()
