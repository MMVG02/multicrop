import tkinter as tk
from tkinter import filedialog, messagebox, Listbox, simpledialog # Added simpledialog for renaming
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid # To generate unique IDs for crops internally
import math # For ceiling function in centering

# --- Constants ---
RECT_TAG_PREFIX = "crop_rect_"
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
MIN_CROP_SIZE = 10 # Minimum width/height for a crop in pixels
# OUTPUT_FOLDER generation is now dynamic based on image name

# --- Main Application Class ---
class MultiCropApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Multi Image Cropper (Improved)")
        self.geometry("1100x750") # Slightly larger for better layout
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        # --- State Variables ---
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.tk_image = None
        self.canvas_image_id = None

        # Crop Data Management
        self.crops = {}           # {crop_id: {'coords': (x1,y1,x2,y2), 'name': display_name, 'rect_id': canvas_rect_id}}
        self.crop_order = []      # List of crop_ids maintaining the user-defined order
        self.used_crop_numbers = set() # Set to track numbers used in default names (e.g., {1, 2, 4})
        self.selected_crop_ids = [] # Can hold multiple IDs for multi-delete

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
        self.last_click_item_id = None # Store ID of item under last press for potential move

        # Zoom/Pan State
        self.zoom_factor = 1.0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_panning = False
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0

        # Listbox Drag & Drop State
        self.drag_start_index = None

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
        self.control_frame = ctk.CTkFrame(self, width=280) # Slightly wider
        self.control_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False)
        self.control_frame.grid_rowconfigure(4, weight=1) # Listbox row takes expansion
        self.control_frame.grid_columnconfigure(0, weight=1)

        # Buttons
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image", command=self.select_image)
        self.btn_select_image.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        self.btn_save_crops = ctk.CTkButton(self.control_frame, text="Save All Crops", command=self.save_crops, state=tk.DISABLED)
        self.btn_save_crops.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        # Crop List Label
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List (Drag to Reorder, Double-Click to Rename):")
        self.lbl_crop_list.grid(row=2, column=0, padx=10, pady=(10, 0), sticky="w")

        # Crop Listbox Frame (to hold listbox and scrollbar)
        self.listbox_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.listbox_frame.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")
        self.listbox_frame.grid_rowconfigure(0, weight=1)
        self.listbox_frame.grid_columnconfigure(0, weight=1)

        # Scrollbar for Listbox
        self.listbox_scrollbar = ctk.CTkScrollbar(self.listbox_frame, command=None) # Command set later
        self.listbox_scrollbar.grid(row=0, column=1, sticky="ns")

        # Crop Listbox (Light theme adjustments)
        self.crop_listbox = Listbox(self.listbox_frame,
                                    bg='white', fg='black',
                                    selectbackground='#ADD8E6', # Light blue selection
                                    selectforeground='black',
                                    highlightthickness=1, highlightbackground="#CCCCCC",
                                    highlightcolor="#89C4F4",
                                    borderwidth=0, exportselection=False,
                                    selectmode=tk.EXTENDED, # *** CHANGE: Allow multi-select ***
                                    yscrollcommand=self.listbox_scrollbar.set) # Link scrollbar
        self.crop_listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox_scrollbar.configure(command=self.crop_listbox.yview) # Link scrollbar back

        # Delete Button (text changed for multi-select)
        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete Selected Crop(s)", command=self.delete_selected_crops, state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crop.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")

        # --- Bindings ---
        # Canvas Bindings
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click) # *** ADDED: Double click ***
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1))
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1))
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press)
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.update_cursor)

        # Listbox Bindings
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.crop_listbox.bind("<Double-Button-1>", self.on_listbox_double_click) # *** ADDED: Rename ***
        self.crop_listbox.bind("<ButtonPress-1>", self.on_listbox_press)      # *** ADDED: Drag Start ***
        self.crop_listbox.bind("<B1-Motion>", self.on_listbox_drag)          # *** ADDED: Drag Motion ***
        self.crop_listbox.bind("<ButtonRelease-1>", self.on_listbox_release)    # *** ADDED: Drag End ***


        # Global Key Bindings
        self.bind("<Delete>", self.delete_selected_crops_event) # Changed to plural method
        self.bind("<BackSpace>", self.delete_selected_crops_event) # MacOS delete key
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
                print("Warning: Canvas size not available for initial fit.")
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

            self.clear_all_crops() # Reset everything for new image
            self.display_image_on_canvas()
            self.btn_save_crops.configure(state=tk.DISABLED)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or process image:\n{e}")
            self.image_path = None
            self.original_image = None
            self.clear_all_crops()
            self.canvas.delete("all")
            self.tk_image = None
            self.display_image = None
            self.btn_save_crops.configure(state=tk.DISABLED)

    def clear_all_crops(self):
        """Clears all crop data, listbox, order, numbers, and selection."""
        self.canvas.delete("crop_rect")
        self.crops.clear()
        self.crop_order = []
        self.used_crop_numbers = set()
        self.selected_crop_ids = []
        self.crop_listbox.delete(0, tk.END)
        self.update_button_states()

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
        self.canvas.delete("all") # Clear everything first
        int_offset_x = int(round(self.canvas_offset_x))
        int_offset_y = int(round(self.canvas_offset_y))

        self.canvas_image_id = self.canvas.create_image(
            int_offset_x, int_offset_y,
            anchor=tk.NW, image=self.tk_image, tags="image"
        )
        self.redraw_all_crops() # Redraw crops respecting new zoom/pan

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
    def find_available_crop_number(self):
        """Finds the smallest positive integer not in self.used_crop_numbers."""
        i = 1
        while i in self.used_crop_numbers:
            i += 1
        return i

    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        if not self.original_image: return

        img_w, img_h = self.original_image.size
        x1_img = max(0, min(x1_img, img_w))
        y1_img = max(0, min(y1_img, img_h))
        x2_img = max(0, min(x2_img, img_w))
        y2_img = max(0, min(y2_img, img_h))

        if abs(x2_img - x1_img) < MIN_CROP_SIZE or abs(y2_img - y1_img) < MIN_CROP_SIZE:
            print("Crop too small, ignoring.")
            if self.current_rect_id: self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            return

        coords = (min(x1_img, x2_img), min(y1_img, y2_img),
                  max(x1_img, x2_img), max(y1_img, y2_img))

        crop_id = str(uuid.uuid4())
        crop_number = self.find_available_crop_number() # *** Use new logic ***
        self.used_crop_numbers.add(crop_number)        # *** Track used number ***

        base_name = os.path.splitext(os.path.basename(self.image_path))[0] if self.image_path else "Image"
        crop_name = f"{base_name}_Crop_{crop_number}" # Default display name

        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])

        if cx1 is None:
            print("Error: Cannot draw crop, coordinate conversion failed.")
            self.used_crop_numbers.discard(crop_number) # Rollback number usage
            return

        rect_id = self.canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH,
            tags=(RECT_TAG_PREFIX + crop_id, "crop_rect") # Assign unique tag
        )

        self.crops[crop_id] = {'coords': coords, 'name': crop_name, 'rect_id': rect_id}
        self.crop_order.append(crop_id) # Add to the end of the ordered list

        # Add to listbox and select it
        self.rebuild_listbox() # Rebuild to ensure order is correct
        new_index = self.crop_order.index(crop_id)
        self.crop_listbox.selection_clear(0, tk.END)
        self.crop_listbox.selection_set(new_index)
        self.on_listbox_select() # Trigger selection logic

        self.update_button_states()

    def get_crop_id_from_list_index(self, index):
        """ Safely get crop_id from listbox index using self.crop_order. """
        if 0 <= index < len(self.crop_order):
            return self.crop_order[index]
        return None

    def get_list_index_from_crop_id(self, crop_id):
        """ Safely get listbox index from crop_id using self.crop_order. """
        try:
            return self.crop_order.index(crop_id)
        except ValueError:
            return -1

    def select_crops(self, crop_ids_to_select):
        """Selects one or more crops by ID, updating visuals."""
        # Deselect previously selected crops visually
        for prev_id in self.selected_crop_ids:
            if prev_id in self.crops:
                rect_id = self.crops[prev_id]['rect_id']
                if rect_id in self.canvas.find_withtag(rect_id):
                     self.canvas.itemconfig(rect_id, outline=DEFAULT_RECT_COLOR)

        self.selected_crop_ids = list(crop_ids_to_select) # Make a copy

        # Select new ones visually
        for crop_id in self.selected_crop_ids:
            if crop_id in self.crops:
                rect_id = self.crops[crop_id]['rect_id']
                if rect_id in self.canvas.find_withtag(rect_id):
                     self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR)
                     self.canvas.tag_raise(rect_id) # Bring selected rects to front
                else:
                    print(f"Warning: Stale rectangle ID {rect_id} for crop {crop_id}")
                    # Optionally remove invalid ID from selection here
            else:
                 print(f"Warning: Attempted to select non-existent crop ID {crop_id}")
                 # Optionally remove invalid ID from selection here

        self.update_button_states()

        # Ensure listbox selection matches (might trigger on_listbox_select again)
        self.update_listbox_selection_visuals()


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
                 return False # Update failed (minimum size violation)

             self.crops[crop_id]['coords'] = (final_x1, final_y1, final_x2, final_y2)
             return True # Indicate update success
        return False

    def redraw_all_crops(self):
        """Redraws all rectangles based on stored coords, order, and current view."""
        all_canvas_items_ids = set(self.canvas.find_all()) # More efficient lookup

        # Draw based on self.crop_order to respect Z-order if needed (though raise handles it mostly)
        for crop_id in self.crop_order:
            if crop_id not in self.crops: continue # Should not happen if sync is correct
            data = self.crops[crop_id]
            img_x1, img_y1, img_x2, img_y2 = data['coords']
            cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1)
            cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)

            if cx1 is None: continue # Conversion failed

            color = SELECTED_RECT_COLOR if crop_id in self.selected_crop_ids else DEFAULT_RECT_COLOR
            tags_tuple = (RECT_TAG_PREFIX + crop_id, "crop_rect")

            rect_id = data.get('rect_id') # Use .get() for safety

            if rect_id and rect_id in all_canvas_items_ids:
                 self.canvas.coords(rect_id, cx1, cy1, cx2, cy2)
                 self.canvas.itemconfig(rect_id, outline=color, tags=tags_tuple)
            else:
                 # Recreate if missing or ID was invalid
                 new_rect_id = self.canvas.create_rectangle(
                     cx1, cy1, cx2, cy2,
                     outline=color, width=RECT_WIDTH,
                     tags=tags_tuple
                 )
                 self.crops[crop_id]['rect_id'] = new_rect_id # Update stored ID

        # Ensure selected are on top
        for sel_id in self.selected_crop_ids:
             if sel_id in self.crops and 'rect_id' in self.crops[sel_id]:
                  rect_id_to_raise = self.crops[sel_id]['rect_id']
                  if rect_id_to_raise in all_canvas_items_ids:
                       self.canvas.tag_raise(rect_id_to_raise)


    def delete_selected_crops_event(self, event=None):
        """Handles delete key press."""
        self.delete_selected_crops()

    def delete_selected_crops(self):
        """Deletes all currently selected crops."""
        indices_to_delete = self.crop_listbox.curselection()
        if not indices_to_delete:
            # Maybe selection comes from canvas? Use self.selected_crop_ids
            if not self.selected_crop_ids: return # Nothing to delete
            ids_to_delete = list(self.selected_crop_ids) # Use internal list
        else:
            # Get IDs from listbox indices
            ids_to_delete = [self.get_crop_id_from_list_index(i) for i in indices_to_delete]
            ids_to_delete = [id for id in ids_to_delete if id] # Filter out None if index was bad

        if not ids_to_delete: return

        deleted_count = 0
        for crop_id in ids_to_delete:
            if crop_id in self.crops:
                data = self.crops[crop_id]

                # Free up the number used in the default name
                try:
                    # Extract number from the *current* name (might have been renamed)
                    # Find the number after the last underscore
                    parts = data['name'].split('_')
                    if len(parts) > 1 and parts[-1].isdigit():
                        num = int(parts[-1])
                        self.used_crop_numbers.discard(num) # *** Release number ***
                except (ValueError, IndexError):
                    print(f"Could not parse number from crop name: {data['name']}")


                # Remove from canvas
                rect_id = data.get('rect_id')
                if rect_id and rect_id in self.canvas.find_all():
                    self.canvas.delete(rect_id)

                # Remove from internal dictionary
                del self.crops[crop_id]
                deleted_count += 1


        # Remove from order list *after* iterating
        self.crop_order = [id for id in self.crop_order if id not in ids_to_delete]

        # Clear internal selection state
        self.selected_crop_ids = []

        # Rebuild the listbox entirely to reflect deletions and potentially changed order
        self.rebuild_listbox()

        print(f"Deleted {deleted_count} crop(s).")
        self.update_button_states() # Update buttons (Save, Delete)

    def rebuild_listbox(self):
        """Clears and repopulates the listbox based on self.crop_order."""
        self.crop_listbox.delete(0, tk.END)
        for crop_id in self.crop_order:
            if crop_id in self.crops:
                self.crop_listbox.insert(tk.END, self.crops[crop_id]['name'])
            else:
                print(f"Warning: crop_id {crop_id} in order list but not in crops dict during rebuild.")
        # Selection visuals will be updated by update_listbox_selection_visuals() if needed


    def update_button_states(self):
        """ Enable/disable buttons based on current state. """
        has_crops = bool(self.crops)
        has_selection = bool(self.selected_crop_ids)

        self.btn_save_crops.configure(state=tk.NORMAL if has_crops else tk.DISABLED)
        self.btn_delete_crop.configure(state=tk.NORMAL if has_selection else tk.DISABLED)


    # --- Mouse Event Handlers (Canvas) ---
    def on_mouse_press(self, event):
        self.canvas.focus_set()
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        self.last_click_item_id = None # Reset

        # Check for resize handle first (only if exactly one crop is selected)
        handle = None
        if len(self.selected_crop_ids) == 1:
             handle = self.get_resize_handle(canvas_x, canvas_y, self.selected_crop_ids[0])

        if handle:
            self.is_resizing = True
            self.resize_handle = handle
            self.start_x = canvas_x
            self.start_y = canvas_y
            # Store original image coords *before* resizing starts
            self.start_coords_img = self.crops[self.selected_crop_ids[0]]['coords']
            return

        # Check if clicking inside an existing rectangle to select/move it
        item_id = self.find_topmost_crop_rect(canvas_x, canvas_y)

        if item_id:
            tags = self.canvas.gettags(item_id)
            clicked_crop_id = None
            if tags and tags[0].startswith(RECT_TAG_PREFIX):
                 clicked_crop_id = tags[0][len(RECT_TAG_PREFIX):]

            if clicked_crop_id and clicked_crop_id in self.crops:
                # If already selected, prepare for moving
                if clicked_crop_id in self.selected_crop_ids:
                    self.is_moving = True
                    # Calculate offset relative to top-left corner for smooth dragging
                    rect_coords = self.canvas.coords(item_id)
                    self.move_offset_x = canvas_x - rect_coords[0]
                    self.move_offset_y = canvas_y - rect_coords[1]
                    self.last_click_item_id = item_id # Store for potential move start
                    # Don't change selection if already selected and starting a move
                    return
                else:
                    # Clicked on a different, unselected rectangle - select only this one
                    self.select_crops([clicked_crop_id]) # Select only this one
                    # Update listbox selection to match
                    self.update_listbox_selection_visuals()
                    # Allow move to start immediately after selection
                    self.is_moving = True
                    rect_coords = self.canvas.coords(item_id)
                    self.move_offset_x = canvas_x - rect_coords[0]
                    self.move_offset_y = canvas_y - rect_coords[1]
                    self.last_click_item_id = item_id
                    return

        # If not clicking handle or existing rect, potentially start drawing
        if self.original_image:
             self.is_drawing = True
             self.start_x = canvas_x
             self.start_y = canvas_y
             # Create temporary drawing rectangle
             self.current_rect_id = self.canvas.create_rectangle(
                 self.start_x, self.start_y, self.start_x, self.start_y,
                 outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4),
                 tags=("temp_rect",)
             )
             # Deselect any currently selected crop(s) when starting a new draw
             if self.selected_crop_ids:
                 self.select_crops([])
                 self.update_listbox_selection_visuals()


    def on_mouse_drag(self, event):
        # Prioritize pan over other drags if pan active
        if self.is_panning:
            self.on_pan_drag(event)
            return

        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.is_drawing and self.current_rect_id:
            self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)

        elif self.is_moving and len(self.selected_crop_ids) == 1: # Only move single selection for now
            crop_id = self.selected_crop_ids[0]
            if not crop_id in self.crops: return # Safety check
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
                updated = self.update_crop_coords(crop_id, (img_x1, img_y1, img_x2, img_y2))
                if updated:
                     validated_img_coords = self.crops[crop_id]['coords']
                     cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                     cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                     self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)

        elif self.is_resizing and len(self.selected_crop_ids) == 1 and self.resize_handle:
            crop_id = self.selected_crop_ids[0]
            if not crop_id in self.crops: return # Safety check
            rect_id = self.crops[crop_id]['rect_id']

            ox1_img, oy1_img, ox2_img, oy2_img = self.start_coords_img
            curr_img_x, curr_img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            start_img_x, start_img_y = self.canvas_to_image_coords(self.start_x, self.start_y)

            if curr_img_x is None or start_img_x is None: return

            # Use current mouse pos relative to *original* opposite corner in image coords
            nx1, ny1, nx2, ny2 = ox1_img, oy1_img, ox2_img, oy2_img

            # Adjust the coordinate corresponding to the handle being dragged
            if 'n' in self.resize_handle: ny1 = curr_img_y
            if 's' in self.resize_handle: ny2 = curr_img_y
            if 'w' in self.resize_handle: nx1 = curr_img_x
            if 'e' in self.resize_handle: nx2 = curr_img_x

            updated = self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2))
            if updated:
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
        self.last_click_item_id = None
        self.update_cursor(event) # Reset cursor

    def on_canvas_double_click(self, event):
        """ *** NEW: Handle double-click on canvas to select a crop. *** """
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        item_id = self.find_topmost_crop_rect(canvas_x, canvas_y)

        if item_id:
            tags = self.canvas.gettags(item_id)
            clicked_crop_id = None
            if tags and tags[0].startswith(RECT_TAG_PREFIX):
                 clicked_crop_id = tags[0][len(RECT_TAG_PREFIX):]

            if clicked_crop_id and clicked_crop_id in self.crops:
                # Select only this crop on double click
                self.select_crops([clicked_crop_id])
                self.update_listbox_selection_visuals()
                print(f"Double-clicked and selected: {self.crops[clicked_crop_id]['name']}")


    def find_topmost_crop_rect(self, canvas_x, canvas_y):
        """Finds the topmost item tagged 'crop_rect' under the coordinates."""
        # Use find_overlapping which returns items in stacking order (topmost last)
        overlapping_ids = self.canvas.find_overlapping(canvas_x - 1, canvas_y - 1, canvas_x + 1, canvas_y + 1)
        for item_id in reversed(overlapping_ids): # Check topmost first
            tags = self.canvas.gettags(item_id)
            if "crop_rect" in tags:
                return item_id
        return None


    # --- Zoom and Pan Handlers ---
    def on_mouse_wheel(self, event, direction=None):
        if not self.original_image: return
        # Simplified delta calculation
        delta = 0
        if direction: delta = direction # For Linux Button 4/5
        elif hasattr(event, 'delta') and event.delta != 0 : delta = event.delta // abs(event.delta) # Windows/macOS
        elif event.num == 5: delta = -1 # Linux Scroll down
        elif event.num == 4: delta = 1  # Linux Scroll up
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
        # Recalculate offset to keep point under mouse stationary
        self.canvas_offset_x = canvas_x - (img_x_before * self.zoom_factor)
        self.canvas_offset_y = canvas_y - (img_y_before * self.zoom_factor)

        self.display_image_on_canvas() # This also redraws crops

    def on_pan_press(self, event):
        if not self.original_image: return
        # Check if drawing/resizing/moving active, if so, ignore pan
        if self.is_drawing or self.is_resizing or self.is_moving:
            return
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

        # Move all canvas items
        self.canvas.move("all", dx, dy)

        self.pan_start_x = current_x
        self.pan_start_y = current_y

    def on_pan_release(self, event):
        if self.is_panning:
            self.is_panning = False
            self.update_cursor(event)


    # --- Listbox Event Handlers ---
    def on_listbox_select(self, event=None):
        """Handles selection changes in the listbox."""
        selected_indices = self.crop_listbox.curselection()

        # Get corresponding crop_ids from the indices using self.crop_order
        selected_ids_from_list = [self.get_crop_id_from_list_index(i) for i in selected_indices]
        selected_ids_from_list = [id for id in selected_ids_from_list if id and id in self.crops] # Filter valid IDs

        # Update internal selection state ONLY IF it differs from listbox state
        # This prevents potential infinite loops if called programmatically
        if set(self.selected_crop_ids) != set(selected_ids_from_list):
            self.select_crops(selected_ids_from_list)
            # No need to call update_listbox_selection_visuals here, as this event originated from the listbox


    def update_listbox_selection_visuals(self):
        """ Ensures the listbox selection visually matches self.selected_crop_ids. """
        # Block the <<ListboxSelect>> event temporarily to prevent feedback loops
        self.crop_listbox.unbind("<<ListboxSelect>>")

        self.crop_listbox.selection_clear(0, tk.END)
        indices_to_select = []
        for crop_id in self.selected_crop_ids:
            index = self.get_list_index_from_crop_id(crop_id)
            if index != -1:
                indices_to_select.append(index)

        for index in indices_to_select:
             self.crop_listbox.selection_set(index)
             self.crop_listbox.activate(index) # Make one active for keyboard navigation
             self.crop_listbox.see(index)     # Ensure visible

        # Re-enable the event binding
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)


    def on_listbox_double_click(self, event):
        """ *** NEW: Handle double-click in Listbox for renaming. *** """
        selected_indices = self.crop_listbox.curselection()
        if len(selected_indices) == 1: # Only allow renaming one at a time
            index = selected_indices[0]
            crop_id = self.get_crop_id_from_list_index(index)
            if crop_id and crop_id in self.crops:
                self.prompt_rename_crop(crop_id, index)


    def prompt_rename_crop(self, crop_id, list_index):
        """ Shows a dialog to rename the selected crop. """
        current_name = self.crops[crop_id]['name']
        new_name = simpledialog.askstring("Rename Crop", f"Enter new name for '{current_name}':",
                                          initialvalue=current_name, parent=self)
        if new_name and new_name != current_name:
            # Optional: Check for name conflicts if desired
            # for other_id, data in self.crops.items():
            #     if other_id != crop_id and data['name'] == new_name:
            #         messagebox.showwarning("Rename Failed", f"Name '{new_name}' already exists.")
            #         return

            print(f"Renaming crop {crop_id} from '{current_name}' to '{new_name}'")
            self.crops[crop_id]['name'] = new_name
            # Update the listbox display
            self.crop_listbox.delete(list_index)
            self.crop_listbox.insert(list_index, new_name)
            # Reselect the renamed item
            self.crop_listbox.selection_set(list_index)
            self.on_listbox_select() # Update internal state if needed

    # --- Listbox Drag & Drop ---
    def on_listbox_press(self, event):
        """ Record the starting index for a potential drag. """
        # Check if click is on an actual item
        self.drag_start_index = self.crop_listbox.nearest(event.y)
        # Ensure the click was roughly within the item bounds horizontally too
        x_in_widget = event.x - self.crop_listbox.winfo_rootx()
        item_bbox = self.crop_listbox.bbox(self.drag_start_index)
        if not item_bbox or not (item_bbox[0] <= x_in_widget <= item_bbox[0] + item_bbox[2]):
            self.drag_start_index = None # Click was not on an item text


    def on_listbox_drag(self, event):
        """ Handle dragging motion within the listbox. """
        if self.drag_start_index is None:
            return # No drag initiated properly

        current_index = self.crop_listbox.nearest(event.y)
        if current_index != self.drag_start_index:
            # Visual cue: Change cursor or highlight insertion point (optional, more complex)
            self.crop_listbox.config(cursor="hand2") # Indicate dragging
            pass # Actual move happens on release


    def on_listbox_release(self, event):
        """ Complete the drag and drop operation. """
        if self.drag_start_index is None:
            self.crop_listbox.config(cursor="") # Reset cursor if drag didn't start properly
            # This release might also trigger a selection change if it wasn't a valid drag start
            self.on_listbox_select()
            return

        start_index = self.drag_start_index
        end_index = self.crop_listbox.nearest(event.y)
        self.drag_start_index = None # Reset drag state
        self.crop_listbox.config(cursor="") # Reset cursor

        # Ensure the target index is valid
        if not (0 <= end_index < self.crop_listbox.size()):
             # Dropped outside the list bounds, treat as no-op or drop at end?
             # Let's treat as no-op for simplicity
             print("Drop outside list bounds, cancelling reorder.")
             # Need to ensure selection reflects the item clicked initially if it wasn't moved
             self.crop_listbox.selection_clear(0, tk.END)
             self.crop_listbox.selection_set(start_index)
             self.on_listbox_select()
             return


        if start_index == end_index:
             # Clicked without dragging significantly, handle as normal selection
             # The <<ListboxSelect>> binding should handle this naturally.
             # We just need to ensure the cursor is reset.
             return


        print(f"Moving item from index {start_index} to {end_index}")

        # Get the crop_id being moved
        moved_crop_id = self.get_crop_id_from_list_index(start_index)
        if not moved_crop_id:
            print("Error: Could not find crop_id for dragged item.")
            return

        # Reorder the internal self.crop_order list
        self.crop_order.pop(start_index)
        self.crop_order.insert(end_index, moved_crop_id)

        # Rebuild the listbox to reflect the new order
        self.rebuild_listbox()

        # Restore selection to the moved item at its new position
        new_index = self.get_list_index_from_crop_id(moved_crop_id)
        if new_index != -1:
             self.crop_listbox.selection_set(new_index)
             self.on_listbox_select() # Update internal selection and button states

    # --- Resizing Helpers ---
    def get_resize_handle(self, canvas_x, canvas_y, crop_id):
        """Checks if the cursor is near a resize handle of the specified crop."""
        if not crop_id or crop_id not in self.crops:
            return None

        rect_id = self.crops[crop_id].get('rect_id')
        if not rect_id or rect_id not in self.canvas.find_all():
            return None

        cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
        handle_margin = 6 # Pixels

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
            new_cursor = "fleur"
        elif self.is_resizing:
            handle = self.resize_handle
            if handle in ('nw', 'se'): new_cursor = "size_nw_se"
            elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
            elif handle in ('n', 's'): new_cursor = "size_ns"
            elif handle in ('e', 'w'): new_cursor = "size_we"
            else: new_cursor = "" # Should not happen during resize
        elif self.is_drawing:
             new_cursor = "crosshair" # Indicate drawing mode
        else:
            new_cursor = "" # Default arrow
            if event: # Only check hover if event provided
                canvas_x = self.canvas.canvasx(event.x)
                canvas_y = self.canvas.canvasy(event.y)
                handle = None
                hover_move = False
                # Only check handles/move if exactly one item is selected
                if len(self.selected_crop_ids) == 1:
                    selected_id = self.selected_crop_ids[0]
                    handle = self.get_resize_handle(canvas_x, canvas_y, selected_id)
                    if not handle:
                         # Check if inside the selected rectangle
                         item_id = self.find_topmost_crop_rect(canvas_x, canvas_y)
                         if item_id:
                             tags = self.canvas.gettags(item_id)
                             hover_crop_id = None
                             if tags and tags[0].startswith(RECT_TAG_PREFIX):
                                  hover_crop_id = tags[0][len(RECT_TAG_PREFIX):]
                             if hover_crop_id == selected_id:
                                 hover_move = True

                if handle:
                    if handle in ('nw', 'se'): new_cursor = "size_nw_se"
                    elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
                    elif handle in ('n', 's'): new_cursor = "size_ns"
                    elif handle in ('e', 'w'): new_cursor = "size_we"
                elif hover_move:
                    new_cursor = "fleur" # Hovering over selected, movable item

        if self.canvas.cget("cursor") != new_cursor:
             self.canvas.config(cursor=new_cursor)

    # --- Window Resize Handling ---
    def on_window_resize(self, event=None):
        # Maybe redraw canvas content if needed, but zoom/pan usually sufficient
        # self.display_image_on_canvas() # Uncomment cautiously, might be slow
        pass


    # --- Saving Crops ---
    def save_crops(self):
        if not self.original_image or not self.image_path:
            messagebox.showwarning("No Image", "Please select an image first.")
            return
        if not self.crops:
            messagebox.showwarning("No Crops", "Please define at least one crop area.")
            return

        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        # Save in a subfolder named after the image, located where the script is run
        output_dir_base = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
        output_dir = os.path.join(output_dir_base, base_name) # Folder name = image base name

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Directory Error", f"Could not create output directory:\n{output_dir}\nError: {e}")
            return

        saved_count = 0
        error_count = 0

        # *** Iterate through self.crop_order to save in the user-defined sequence ***
        for i, crop_id in enumerate(self.crop_order):
            if crop_id not in self.crops:
                print(f"Warning: Skipping crop ID {crop_id} as it's not in the crops dictionary.")
                error_count += 1
                continue

            data = self.crops[crop_id]
            coords = tuple(map(int, data['coords']))
            # *** Filename uses the order index (1-based) ***
            filename = f"{base_name}_{i + 1}.jpg"
            filepath = os.path.join(output_dir, filename)

            try:
                cropped_img = self.original_image.crop(coords)
                # Convert to RGB if necessary (e.g., from RGBA or P mode) before saving as JPEG
                if cropped_img.mode == 'RGBA':
                    # Create a white background image
                    bg = Image.new('RGB', cropped_img.size, (255, 255, 255))
                    # Paste the RGBA image onto the background using the alpha channel as mask
                    bg.paste(cropped_img, (0, 0), cropped_img)
                    cropped_img = bg
                elif cropped_img.mode == 'P':
                     cropped_img = cropped_img.convert('RGB')

                cropped_img.save(filepath, "JPEG", quality=95) # Good default quality
                saved_count += 1
            except Exception as e:
                error_count += 1
                print(f"Error saving {filename} (Crop ID: {crop_id}): {e}")
                # Optionally show more detailed error to user or log it
                # messagebox.showerror("Save Error", f"Failed to save {filename}:\n{e}") # Could be annoying if many errors

        # Show summary message
        if error_count == 0:
            messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to the '{os.path.basename(output_dir)}' folder.")
        else:
            messagebox.showwarning("Partial Success", f"Saved {saved_count} crops to '{os.path.basename(output_dir)}'.\nFailed to save {error_count} crops. Check console for details.")


# --- Run the Application ---
if __name__ == "__main__":
    app = MultiCropApp()
    app.mainloop()
