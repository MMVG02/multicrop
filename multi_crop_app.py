import tkinter as tk
from tkinter import filedialog, messagebox, Listbox
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid # To generate unique IDs for crops internally
import math # For ceiling function in centering
import re   # For parsing crop numbers

# --- Constants ---
RECT_TAG_PREFIX = "crop_rect_"
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
MIN_CROP_SIZE = 10 # Minimum width/height for a crop in pixels
DEFAULT_CROP_NAME_PATTERN = r"^(.*)_Crop_(\d+)$" # Regex to parse default names

# --- Main Application Class ---
class MultiCropApp(ctk.CTk):
    def __init__(self): # Corrected from init
        super().__init__()

        # --- Window Setup ---
        self.title("Multi Image Cropper")
        self.geometry("1100x750") # Slightly larger for new buttons

        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        # --- State Variables ---
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.tk_image = None
        self.canvas_image_id = None
        # { crop_id (uuid): {'coords': (img_x1,y1,x2,y2), 'name': display_name, 'rect_id': canvas_rect_id} }
        self.crops = {}
        self.selected_crop_ids = set() # Use a set for potentially multiple selections

        # Drawing/Editing State
        self.start_x, self.start_y = None, None
        self.current_rect_id = None
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.move_offset_x, self.move_offset_y = 0, 0
        self.start_coords_img = None # Store original coords during resize/move

        # Zoom/Pan State
        self.zoom_factor = 1.0
        self.pan_start_x, self.pan_start_y = 0, 0
        self.is_panning = False
        self.canvas_offset_x, self.canvas_offset_y = 0, 0

        # --- UI Layout ---
        self.grid_columnconfigure(0, weight=3) # Image area
        self.grid_columnconfigure(1, weight=1) # Control panel
        self.grid_rowconfigure(0, weight=1)

        # --- Left Frame (Image Display) ---
        self.image_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.image_frame, bg="gray90", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # --- Right Frame (Controls) ---
        self.control_frame = ctk.CTkFrame(self, width=300) # Increased width slightly
        self.control_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False)
        self.control_frame.grid_columnconfigure(0, weight=1)
        self.control_frame.grid_columnconfigure(1, weight=1) # For Up/Down buttons
        self.control_frame.grid_rowconfigure(4, weight=1) # Listbox row

        # Buttons
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image", command=self.select_image)
        self.btn_select_image.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew")

        self.btn_save_crops = ctk.CTkButton(self.control_frame, text="Save All Crops", command=self.save_crops, state=tk.DISABLED)
        self.btn_save_crops.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

        # Crop List Label
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List (Double-click to rename):")
        self.lbl_crop_list.grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w")

        # Reorder Buttons Frame
        self.reorder_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.reorder_frame.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="ew")
        self.reorder_frame.grid_columnconfigure(0, weight=1)
        self.reorder_frame.grid_columnconfigure(1, weight=1)

        self.btn_move_up = ctk.CTkButton(self.reorder_frame, text="Move Up", command=self.move_crop_up, state=tk.DISABLED)
        self.btn_move_up.grid(row=0, column=0, padx=(0, 2), pady=0, sticky="ew")

        self.btn_move_down = ctk.CTkButton(self.reorder_frame, text="Move Down", command=self.move_crop_down, state=tk.DISABLED)
        self.btn_move_down.grid(row=0, column=1, padx=(2, 0), pady=0, sticky="ew")

        # Crop Listbox
        self.crop_listbox = Listbox(self.control_frame,
                                    bg='white', fg='black',
                                    selectbackground='#CDEAFE', selectforeground='black',
                                    highlightthickness=1, highlightbackground="#CCCCCC",
                                    highlightcolor="#89C4F4", borderwidth=0,
                                    exportselection=False,
                                    selectmode=tk.EXTENDED) # Allow multi-select
        self.crop_listbox.grid(row=4, column=0, columnspan=2, padx=10, pady=0, sticky="nsew")
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.crop_listbox.bind("<Double-Button-1>", self.on_listbox_double_click) # Rename binding

        # Delete Button
        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete Selected", command=self.delete_selected_crops, state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crop.grid(row=5, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="ew")

        # --- Canvas Bindings ---
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<ButtonPress-3>", self.on_mouse_right_press) # Right-click select
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1)) # Linux scroll up
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1)) # Linux scroll down
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press) # Middle mouse button pan
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.update_cursor)
        self.bind("<Delete>", self.delete_selected_crops_event) # Bind Delete key
        self.bind("<Configure>", self.on_window_resize)

    # --- Image Handling ---
    def select_image(self):
        path = filedialog.askopenfilename(
            title="Select Image File",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff")]
        )
        if not path:
            return

        try:
            self.image_path = path
            self.original_image = Image.open(self.image_path)

            self.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width, canvas_height = 600, 500 # Fallback

            img_width, img_height = self.original_image.size
            if img_width == 0 or img_height == 0:
                raise ValueError("Image has zero dimension")

            zoom_h = canvas_width / img_width
            zoom_v = canvas_height / img_height
            initial_zoom = min(zoom_h, zoom_v)
            padding_factor = 0.98
            self.zoom_factor = min(1.0, initial_zoom) * padding_factor

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
            self.update_button_states()


    def clear_crops_and_list(self):
        """Clears existing crops, listbox, and resets related states."""
        self.canvas.delete("crop_rect")
        self.crops.clear()
        self.crop_listbox.delete(0, tk.END)
        self.selected_crop_ids.clear()
        self.update_button_states()


    def display_image_on_canvas(self):
        """Displays the current self.display_image on the canvas respecting zoom and pan."""
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
        self.canvas.delete("all") # Clear everything first

        int_offset_x = int(round(self.canvas_offset_x))
        int_offset_y = int(round(self.canvas_offset_y))

        self.canvas_image_id = self.canvas.create_image(
            int_offset_x, int_offset_y,
            anchor=tk.NW, image=self.tk_image, tags="image"
        )
        self.redraw_all_crops()

    # --- Coordinate Conversion ---
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

    # --- Crop Handling ---
    def find_next_crop_number(self, base_name):
        """Finds the smallest available integer N for the crop name."""
        existing_nums = set()
        for data in self.crops.values():
            match = re.match(DEFAULT_CROP_NAME_PATTERN, data['name'])
            if match and match.group(1) == base_name:
                try:
                    existing_nums.add(int(match.group(2)))
                except ValueError:
                    pass # Ignore names that don't parse correctly

        num = 1
        while num in existing_nums:
            num += 1
        return num

    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        """Adds a new crop definition and draws it."""
        if not self.original_image: return

        img_w, img_h = self.original_image.size
        x1_img = max(0, min(x1_img, img_w))
        y1_img = max(0, min(y1_img, img_h))
        x2_img = max(0, min(x2_img, img_w))
        y2_img = max(0, min(y2_img, img_h))

        # Ensure min size and valid coords
        final_x1 = min(x1_img, x2_img)
        final_y1 = min(y1_img, y2_img)
        final_x2 = max(x1_img, x2_img)
        final_y2 = max(y1_img, y2_img)

        if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE:
            print("Crop too small, ignoring.")
            if self.current_rect_id: self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            return

        coords = (final_x1, final_y1, final_x2, final_y2)
        crop_id = str(uuid.uuid4()) # Internal unique ID

        base_name = "Image" # Default
        if self.image_path:
            base_name = os.path.splitext(os.path.basename(self.image_path))[0]

        # Find the next available number for the name
        next_num = self.find_next_crop_number(base_name)
        crop_name = f"{base_name}_Crop_{next_num}"

        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])

        if cx1 is None:
            print("Error: Cannot draw crop, coordinate conversion failed.")
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

        # Add to listbox and select it
        self.crop_listbox.insert(tk.END, crop_name)
        self.crop_listbox.selection_clear(0, tk.END)
        self.crop_listbox.selection_set(tk.END)
        self.on_listbox_select() # Trigger selection logic

        self.update_button_states()


    def select_crop(self, crop_ids_to_select, from_listbox=False):
        """Selects one or more crops by ID, updates visuals."""
        if not isinstance(crop_ids_to_select, set):
             # Handle single ID case or None
            crop_ids_to_select = {crop_ids_to_select} if crop_ids_to_select else set()

        ids_changed = self.selected_crop_ids != crop_ids_to_select

        if not ids_changed:
             return # No change in selection

        # Deselect previously selected rectangles that are no longer selected
        ids_to_deselect = self.selected_crop_ids - crop_ids_to_select
        for crop_id in ids_to_deselect:
            if crop_id in self.crops:
                rect_id = self.crops[crop_id]['rect_id']
                if rect_id in self.canvas.find_withtag(rect_id):
                    self.canvas.itemconfig(rect_id, outline=DEFAULT_RECT_COLOR)

        # Select newly selected rectangles
        ids_to_select_new = crop_ids_to_select - self.selected_crop_ids
        for crop_id in ids_to_select_new:
            if crop_id in self.crops:
                rect_id = self.crops[crop_id]['rect_id']
                if rect_id in self.canvas.find_withtag(rect_id):
                    self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR)
                    self.canvas.tag_raise(rect_id) # Bring selected to front
                else:
                    print(f"Warning: Stale rectangle ID {rect_id} for crop {crop_id}")
                    # Remove invalid ID from selection if necessary
                    crop_ids_to_select.discard(crop_id)


        self.selected_crop_ids = crop_ids_to_select

        # Update listbox selection if the call didn't originate from it
        if not from_listbox:
            self.crop_listbox.selection_clear(0, tk.END)
            indices_to_select = []
            list_items = self.crop_listbox.get(0, tk.END)
            for crop_id in self.selected_crop_ids:
                 if crop_id in self.crops:
                     name_to_find = self.crops[crop_id]['name']
                     try:
                         index = list_items.index(name_to_find)
                         indices_to_select.append(index)
                     except ValueError:
                         pass # Name not found in listbox? Should not happen.

            for index in indices_to_select:
                self.crop_listbox.selection_set(index)
                self.crop_listbox.activate(index)
            if indices_to_select:
                 self.crop_listbox.see(indices_to_select[-1]) # Ensure last selected is visible

        self.update_button_states()


    def update_crop_coords(self, crop_id, new_img_coords):
        """Updates the stored original image coordinates for a crop."""
        if crop_id in self.crops and self.original_image:
            img_w, img_h = self.original_image.size
            x1, y1, x2, y2 = new_img_coords

            # Clamp coordinates
            x1 = max(0, min(x1, img_w))
            y1 = max(0, min(y1, img_h))
            x2 = max(0, min(x2, img_w))
            y2 = max(0, min(y2, img_h))

            # Ensure x1 < x2, y1 < y2 and minimum size
            final_x1 = min(x1, x2)
            final_y1 = min(y1, y2)
            final_x2 = max(x1, x2)
            final_y2 = max(y1, y2)

            if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE:
                # print("Debug: Crop update rejected due to min size violation")
                return False # Indicate update failed

            self.crops[crop_id]['coords'] = (final_x1, final_y1, final_x2, final_y2)
            return True # Indicate update success
        return False


    def redraw_all_crops(self):
        """Redraws all rectangles based on stored coords and current view."""
        all_canvas_items = self.canvas.find_all() # Get current items once

        for crop_id, data in self.crops.items():
            img_x1, img_y1, img_x2, img_y2 = data['coords']
            cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1)
            cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)

            if cx1 is None: continue # Skip if conversion fails

            color = SELECTED_RECT_COLOR if crop_id in self.selected_crop_ids else DEFAULT_RECT_COLOR
            tags_tuple = (RECT_TAG_PREFIX + crop_id, "crop_rect")

            if data['rect_id'] in all_canvas_items:
                self.canvas.coords(data['rect_id'], cx1, cy1, cx2, cy2)
                self.canvas.itemconfig(data['rect_id'], outline=color, tags=tags_tuple)
            else:
                # Recreate if missing (e.g., after image reload)
                rect_id = self.canvas.create_rectangle(
                    cx1, cy1, cx2, cy2,
                    outline=color, width=RECT_WIDTH,
                    tags=tags_tuple
                )
                self.crops[crop_id]['rect_id'] = rect_id # Update stored ID

        # Ensure selected are on top after all are drawn/updated
        for crop_id in self.selected_crop_ids:
             if crop_id in self.crops:
                 selected_rect_id = self.crops[crop_id]['rect_id']
                 if selected_rect_id in self.canvas.find_all():
                     self.canvas.tag_raise(selected_rect_id)


    def delete_selected_crops_event(self, event=None):
        """Handles delete key press."""
        self.delete_selected_crops()

    def delete_selected_crops(self):
        """Deletes the currently selected crops (can be multiple)."""
        selected_indices = self.crop_listbox.curselection()
        if not selected_indices:
            return

        # Get names before deleting from listbox
        names_to_delete = [self.crop_listbox.get(i) for i in selected_indices]

        ids_to_delete = set()
        for name in names_to_delete:
            for crop_id, data in self.crops.items():
                if data['name'] == name:
                    ids_to_delete.add(crop_id)
                    break # Found the ID for this name

        if not ids_to_delete:
            return # Should not happen if listbox selection is synced

        # Delete from canvas and internal dictionary
        for crop_id in ids_to_delete:
            if crop_id in self.crops:
                data = self.crops[crop_id]
                if data['rect_id'] in self.canvas.find_all():
                    self.canvas.delete(data['rect_id'])
                del self.crops[crop_id]

        # Delete from listbox (iterate in reverse to avoid index issues)
        for index in sorted(selected_indices, reverse=True):
            self.crop_listbox.delete(index)

        # Clear selection state
        self.selected_crop_ids.clear()
        self.update_button_states()


    def update_button_states(self):
        """Updates the enabled/disabled state of buttons based on current state."""
        has_image = self.original_image is not None
        has_crops = bool(self.crops)
        selection = self.crop_listbox.curselection()
        num_selected = len(selection)

        # Save button
        self.btn_save_crops.configure(state=tk.NORMAL if has_image and has_crops else tk.DISABLED)

        # Delete button
        self.btn_delete_crop.configure(state=tk.NORMAL if num_selected > 0 else tk.DISABLED)

        # Move Up/Down buttons
        can_move_up = False
        can_move_down = False
        if num_selected == 1: # Only allow moving single items
            idx = selection[0]
            if idx > 0:
                can_move_up = True
            if idx < self.crop_listbox.size() - 1:
                can_move_down = True

        self.btn_move_up.configure(state=tk.NORMAL if can_move_up else tk.DISABLED)
        self.btn_move_down.configure(state=tk.NORMAL if can_move_down else tk.DISABLED)


    # --- Mouse Event Handlers ---
    def find_crop_id_at(self, canvas_x, canvas_y):
        """Finds the topmost crop ID at the given canvas coordinates."""
        overlapping_items = self.canvas.find_overlapping(canvas_x-1, canvas_y-1, canvas_x+1, canvas_y+1)
        for item_id in reversed(overlapping_items): # Check topmost first
            tags = self.canvas.gettags(item_id)
            if tags and tags[0].startswith(RECT_TAG_PREFIX) and "crop_rect" in tags:
                crop_id = tags[0][len(RECT_TAG_PREFIX):]
                if crop_id in self.crops:
                    return crop_id
        return None

    def on_mouse_press(self, event):
        self.canvas.focus_set()
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # Check for resize handle click (only if exactly one crop is selected)
        handle = None
        if len(self.selected_crop_ids) == 1:
            handle = self.get_resize_handle(canvas_x, canvas_y)

        if handle:
            self.is_resizing = True
            self.resize_handle = handle
            self.start_x, self.start_y = canvas_x, canvas_y
            # Get the single selected ID
            selected_id = next(iter(self.selected_crop_ids))
            self.start_coords_img = self.crops[selected_id]['coords']
            return

        # Check if clicking inside an existing rectangle to select/move
        clicked_crop_id = self.find_crop_id_at(canvas_x, canvas_y)

        if clicked_crop_id:
            # If Ctrl/Shift is pressed, modify selection, otherwise replace selection
            # Note: Tkinter's event state checking can be platform-dependent.
            # For simplicity, left-click always selects *only* the clicked item for now.
            # Multi-select is handled via the listbox.
            self.select_crop(clicked_crop_id) # Select only this one

            # Start moving if the clicked crop is the *only* selected one
            if len(self.selected_crop_ids) == 1 and clicked_crop_id in self.selected_crop_ids:
                self.is_moving = True
                rect_coords = self.canvas.coords(self.crops[clicked_crop_id]['rect_id'])
                self.move_offset_x = canvas_x - rect_coords[0]
                self.move_offset_y = canvas_y - rect_coords[1]
                self.start_coords_img = self.crops[clicked_crop_id]['coords'] # Store starting point
            return

        # If not clicking handle or existing rect, start drawing new one
        if self.original_image:
            self.is_drawing = True
            self.start_x, self.start_y = canvas_x, canvas_y
            self.current_rect_id = self.canvas.create_rectangle(
                self.start_x, self.start_y, self.start_x, self.start_y,
                outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4),
                tags=("temp_rect",)
            )
            # Deselect any currently selected crop when starting to draw new
            self.select_crop(None)


    def on_mouse_right_press(self, event):
        """Handle right-click to select a rectangle."""
        self.canvas.focus_set()
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        clicked_crop_id = self.find_crop_id_at(canvas_x, canvas_y)

        if clicked_crop_id:
            # Right-click selects ONLY the clicked item, deselecting others
            self.select_crop(clicked_crop_id)
        else:
            # Right-clicking empty space deselects all
            self.select_crop(None)


    def on_mouse_drag(self, event):
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.is_drawing and self.current_rect_id:
            self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)

        elif self.is_moving and len(self.selected_crop_ids) == 1:
            crop_id = next(iter(self.selected_crop_ids)) # Get the single selected ID
            rect_id = self.crops[crop_id]['rect_id']

            # Calculate new top-left canvas coords
            new_cx1 = canvas_x - self.move_offset_x
            new_cy1 = canvas_y - self.move_offset_y

            # Calculate delta in image coords from the start of the move
            start_img_x1, start_img_y1, start_img_x2, start_img_y2 = self.start_coords_img
            img_w = start_img_x2 - start_img_x1
            img_h = start_img_y2 - start_img_y1

            # Convert new canvas top-left to image coords
            new_img_x1, new_img_y1 = self.canvas_to_image_coords(new_cx1, new_cy1)

            if new_img_x1 is not None:
                new_img_x2 = new_img_x1 + img_w
                new_img_y2 = new_img_y1 + img_h

                # Update stored coordinates (includes bounds check)
                updated = self.update_crop_coords(crop_id, (new_img_x1, new_img_y1, new_img_x2, new_img_y2))
                if updated:
                    # Redraw the rect on canvas using validated coords
                    validated_img_coords = self.crops[crop_id]['coords']
                    cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                    cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                    if cx1_final is not None: # Check conversion success
                        self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)

        elif self.is_resizing and len(self.selected_crop_ids) == 1 and self.resize_handle:
            crop_id = next(iter(self.selected_crop_ids)) # Get the single selected ID
            rect_id = self.crops[crop_id]['rect_id']

            ox1_img, oy1_img, ox2_img, oy2_img = self.start_coords_img
            curr_img_x, curr_img_y = self.canvas_to_image_coords(canvas_x, canvas_y)

            if curr_img_x is None: return # Bail if conversion fails

            nx1, ny1, nx2, ny2 = ox1_img, oy1_img, ox2_img, oy2_img

            # Adjust coords based on handle and current mouse pos in image space
            # Important: Adjust the edge corresponding to the handle based on the *current* mouse position
            if 'n' in self.resize_handle: ny1 = curr_img_y
            if 's' in self.resize_handle: ny2 = curr_img_y
            if 'w' in self.resize_handle: nx1 = curr_img_x
            if 'e' in self.resize_handle: nx2 = curr_img_x

            # Update stored coords (includes validation like min size, bounds, x1<x2)
            updated = self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2))
            if updated:
                # Redraw the rect on canvas
                validated_img_coords = self.crops[crop_id]['coords']
                cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                if cx1_final is not None: # Check conversion success
                    self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)


    def on_mouse_release(self, event):
        if self.is_drawing and self.current_rect_id:
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

            # Delete the temporary dashed rect
            if self.current_rect_id in self.canvas.find_withtag("temp_rect"):
                self.canvas.delete(self.current_rect_id)

            img_x1, img_y1 = self.canvas_to_image_coords(self.start_x, self.start_y)
            img_x2, img_y2 = self.canvas_to_image_coords(canvas_x, canvas_y)

            if img_x1 is not None and img_y1 is not None and img_x2 is not None and img_y2 is not None:
                self.add_crop(img_x1, img_y1, img_x2, img_y2)
            else:
                print("Failed to add crop due to coordinate conversion error.")

        # Reset states
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.current_rect_id = None
        self.start_coords_img = None

        self.update_cursor(event) # Reset cursor


    # --- Zoom and Pan Handlers ---
    def on_mouse_wheel(self, event, direction=None):
        if not self.original_image: return

        if direction: delta = direction
        elif event.num == 5 or event.delta < 0: delta = -1
        elif event.num == 4 or event.delta > 0: delta = 1
        else: return

        zoom_increment = 1.1
        min_zoom, max_zoom = 0.01, 20.0

        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)

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
        self.canvas.move("all", dx, dy) # Move image and all rects

        self.pan_start_x = current_x
        self.pan_start_y = current_y


    def on_pan_release(self, event):
        self.is_panning = False
        self.update_cursor(event) # Reset cursor based on current position


    # --- Listbox Selection & Actions ---
    def on_listbox_select(self, event=None):
        """Handles selection changes in the listbox."""
        selected_indices = self.crop_listbox.curselection()
        selected_names = {self.crop_listbox.get(i) for i in selected_indices}

        newly_selected_ids = set()
        for name in selected_names:
            found_id = None
            for crop_id, data in self.crops.items():
                if data['name'] == name:
                    found_id = crop_id
                    break
            if found_id:
                newly_selected_ids.add(found_id)
            else:
                print(f"Warning: Listbox name '{name}' not found in crops dict.")

        # Update internal selection state and visuals, marking it as 'from_listbox'
        self.select_crop(newly_selected_ids, from_listbox=True)


    def on_listbox_double_click(self, event=None):
        """Handles double-click for renaming."""
        selection = self.crop_listbox.curselection()
        if len(selection) != 1: # Only allow renaming single selection
            return
        index = selection[0]
        old_name = self.crop_listbox.get(index)

        # Find the crop_id associated with this name
        crop_id_to_rename = None
        for c_id, data in self.crops.items():
            if data['name'] == old_name:
                crop_id_to_rename = c_id
                break

        if not crop_id_to_rename:
            messagebox.showerror("Error", "Could not find internal data for the selected item.")
            return

        # Simple input dialog for new name
        dialog = ctk.CTkInputDialog(text="Enter new name:", title="Rename Crop")
        new_name = dialog.get_input()

        if new_name and new_name != old_name:
            # Optional: Check if new_name already exists
            name_exists = any(data['name'] == new_name for data in self.crops.values())
            if name_exists:
                messagebox.showwarning("Rename Failed", f"The name '{new_name}' is already in use.")
                return

            # Update internal dictionary
            self.crops[crop_id_to_rename]['name'] = new_name
            # Update listbox
            self.crop_listbox.delete(index)
            self.crop_listbox.insert(index, new_name)
            # Reselect the renamed item
            self.crop_listbox.selection_set(index)
            self.on_listbox_select() # Update states


    def move_crop_up(self):
        selection = self.crop_listbox.curselection()
        if len(selection) != 1: return
        index = selection[0]
        if index > 0:
            text = self.crop_listbox.get(index)
            self.crop_listbox.delete(index)
            self.crop_listbox.insert(index - 1, text)
            self.crop_listbox.selection_set(index - 1)
            self.on_listbox_select() # Update states

    def move_crop_down(self):
        selection = self.crop_listbox.curselection()
        if len(selection) != 1: return
        index = selection[0]
        if index < self.crop_listbox.size() - 1:
            text = self.crop_listbox.get(index)
            self.crop_listbox.delete(index)
            self.crop_listbox.insert(index + 1, text)
            self.crop_listbox.selection_set(index + 1)
            self.on_listbox_select() # Update states


    # --- Resizing Helpers ---
    def get_resize_handle(self, canvas_x, canvas_y):
        """Checks if cursor is near a resize handle of the single selected crop."""
        # This only makes sense if exactly one crop is selected
        if len(self.selected_crop_ids) != 1:
            return None

        selected_id = next(iter(self.selected_crop_ids)) # Get the single ID
        if selected_id not in self.crops: return None

        rect_id = self.crops[selected_id]['rect_id']
        if rect_id not in self.canvas.find_all(): return None

        cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
        handle_margin = 6 # Pixels

        # Check corners
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'nw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'ne'
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'sw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'se'

        # Check edges
        inner_buffer = handle_margin / 2
        if abs(canvas_y - cy1) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 'n'
        if abs(canvas_y - cy2) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 's'
        if abs(canvas_x - cx1) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'w'
        if abs(canvas_x - cx2) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'e'

        return None


    def update_cursor(self, event=None):
        """Changes the mouse cursor based on position."""
        if self.is_panning:
            self.canvas.config(cursor="fleur")
            return
        if self.is_drawing or self.is_resizing or self.is_moving:
            # Let the action handlers manage the cursor during drag
            # (e.g., fleur for moving, specific size cursors for resizing)
             if self.is_moving: self.canvas.config(cursor="fleur")
             # Resizing cursors are set implicitly by Tkinter based on handle,
             # but we can force them if needed. Let's rely on hover logic below.
             return

        new_cursor = "" # Default arrow
        if event:
            canvas_x = self.canvas.canvasx(event.x)
            canvas_y = self.canvas.canvasy(event.y)
            handle = self.get_resize_handle(canvas_x, canvas_y) # Checks if exactly one selected

            if handle:
                if handle in ('nw', 'se'): new_cursor = "size_nw_se"
                elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
                elif handle in ('n', 's'): new_cursor = "size_ns"
                elif handle in ('e', 'w'): new_cursor = "size_we"
            else:
                # Check if hovering inside the single selected rectangle for move indication
                if len(self.selected_crop_ids) == 1:
                    selected_id = next(iter(self.selected_crop_ids))
                    if selected_id in self.crops:
                        rect_id = self.crops[selected_id]['rect_id']
                        if rect_id in self.canvas.find_all():
                            cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
                            if cx1 < canvas_x < cx2 and cy1 < canvas_y < cy2:
                                new_cursor = "fleur" # Indicate movability

        if self.canvas.cget("cursor") != new_cursor:
            self.canvas.config(cursor=new_cursor)


    # --- Window Resize Handling ---
    def on_window_resize(self, event=None):
        # Could potentially recalculate initial zoom/pan if desired,
        # but manual zoom/pan usually suffices after initial load.
        pass

    # --- Saving Crops ---
    def save_crops(self):
        if not self.original_image or not self.image_path:
            messagebox.showwarning("No Image", "Please select an image first.")
            return

        # Get crop names in the current listbox order
        ordered_crop_names = self.crop_listbox.get(0, tk.END)

        if not ordered_crop_names:
            messagebox.showwarning("No Crops", "Please define and order crop areas.")
            return

        # Create output folder named after the image, relative to script/executable
        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        output_dir = os.path.abspath(base_name) # Absolute path

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Directory Error", f"Could not create output directory:\n{output_dir}\n{e}")
            return

        saved_count = 0
        error_count = 0

        # Create a mapping from name to crop data for quick lookup
        name_to_data = {data['name']: data for data in self.crops.values()}

        # Save crops based on the listbox order
        for i, crop_name in enumerate(ordered_crop_names, start=1):
            if crop_name in name_to_data:
                data = name_to_data[crop_name]
                coords = tuple(map(int, data['coords'])) # Ensure integer coords

                # Use sequential numbering based on listbox order for filename
                filename = f"{base_name}_{i}.jpg"
                filepath = os.path.join(output_dir, filename)

                try:
                    cropped_img = self.original_image.crop(coords)
                    # Ensure saving as RGB JPG
                    if cropped_img.mode in ('RGBA', 'P'):
                        cropped_img = cropped_img.convert('RGB')
                    cropped_img.save(filepath, "JPEG", quality=95)
                    saved_count += 1
                except Exception as e:
                    error_count += 1
                    print(f"Error saving {filename}: {e}")
            else:
                error_count += 1
                print(f"Error: Crop name '{crop_name}' from listbox not found in internal data.")


        # Show summary message
        if error_count == 0:
            messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to the '{base_name}' folder.")
        else:
            messagebox.showwarning("Partial Success", f"Saved {saved_count} crops to '{base_name}'.\nFailed to save {error_count} crops (check console/log).")


# --- Run the Application ---
if __name__ == "__main__":
    app = MultiCropApp()
    app.mainloop()
