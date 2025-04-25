import tkinter as tk
from tkinter import filedialog, messagebox, Listbox, simpledialog
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid
import math

# --- Constants ---
RECT_TAG_PREFIX = "crop_rect_"
TEMP_RECT_TAG = "temp_rect"
IMAGE_TAG = "image"
CROP_RECT_TAG = "crop_rect" # Generic tag for all crop rectangles
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
MIN_CROP_SIZE = 10 # Minimum width/height for a crop in pixels

class MultiCropApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Multi Image Cropper")
        self.geometry("1100x750") # Increased size slightly
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        # --- State Variables ---
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.tk_image = None
        self.canvas_image_id = None
        self.crops = {} # {crop_id: {'coords': (x1,y1,x2,y2), 'name': name, 'rect_id': canvas_rect_id}}
        self.crop_order = [] # List of crop_ids defining the order
        self.selected_crop_ids = set() # Store potentially multiple selected IDs

        # Drawing/Editing State
        self.start_x = None
        self.start_y = None
        self.current_rect_id = None # ID for the temporary drawing rect
        self.is_drawing = False
        self.is_moving = False
        self.move_selection_start_coords = {} # Store starting coords for multi-move {crop_id: (x1, y1, x2, y2)}
        self.is_resizing = False
        self.resize_handle = None
        self.resize_crop_id = None # Which crop is being resized
        self.resize_start_coords_img = None # Store original img coords at resize start

        self.move_offset_x = 0
        self.move_offset_y = 0

        # Zoom/Pan State
        self.zoom_factor = 1.0
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.is_panning = False
        self.canvas_offset_x = 0
        self.canvas_offset_y = 0

        # Listbox Drag State
        self.drag_start_index = None
        self.drag_drop_index = None

        self._create_widgets()
        self._bind_events()

    # --- UI Setup ---
    def _create_widgets(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Left Frame (Image Display)
        self.image_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.image_frame, bg="gray90", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Right Frame (Controls)
        self.control_frame = ctk.CTkFrame(self, width=250)
        self.control_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False)
        self.control_frame.grid_rowconfigure(3, weight=1)
        self.control_frame.grid_columnconfigure(0, weight=1)

        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image", command=self.select_image)
        self.btn_select_image.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        self.btn_save_crops = ctk.CTkButton(self.control_frame, text="Save All Crops", command=self.save_crops, state=tk.DISABLED)
        self.btn_save_crops.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List (Double-click to rename):")
        self.lbl_crop_list.grid(row=2, column=0, padx=10, pady=(10, 0), sticky="w")

        # ** Changed to EXTENDED selection **
        self.crop_listbox = Listbox(self.control_frame,
                                     bg='white', fg='black',
                                     selectbackground='#AAD4F5', # Slightly lighter blue
                                     selectforeground='black',
                                     highlightthickness=1, highlightbackground="#CCCCCC",
                                     highlightcolor="#89C4F4",
                                     borderwidth=0, exportselection=False,
                                     selectmode=tk.EXTENDED) # Enable multi-select
        self.crop_listbox.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")

        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete Selected", command=self.delete_selected_crops, state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crop.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")

    # --- Event Bindings ---
    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_left_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_left_release)

        # ** Added Right-click binding **
        self.canvas.bind("<ButtonPress-3>", self.on_canvas_right_click)

        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel) # Windows/macOS
        self.canvas.bind("<Button-4>", lambda e: self.on_mouse_wheel(e, 1)) # Linux scroll up
        self.canvas.bind("<Button-5>", lambda e: self.on_mouse_wheel(e, -1)) # Linux scroll down

        self.canvas.bind("<ButtonPress-2>", self.on_pan_press) # Middle mouse button pan
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)

        self.canvas.bind("<Motion>", self.update_cursor) # For resize handles

        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        # ** Added Listbox Drag and Drop & Rename bindings **
        self.crop_listbox.bind("<ButtonPress-1>", self.on_listbox_drag_start)
        self.crop_listbox.bind("<B1-Motion>", self.on_listbox_drag_motion)
        self.crop_listbox.bind("<ButtonRelease-1>", self.on_listbox_drag_release)
        self.crop_listbox.bind("<Double-Button-1>", self.on_listbox_double_click)

        self.bind("<Delete>", self.delete_selected_crops_event)
        self.bind("<BackSpace>", self.delete_selected_crops_event) # Also bind Backspace for Mac
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
            new_image = Image.open(path)
            self.image_path = path
            self.original_image = new_image
            self.clear_all_crops() # Clear previous state
            self._fit_image_to_canvas() # Calculate initial zoom and offset
            self.display_image_on_canvas() # Display the new image
            self.btn_save_crops.configure(state=tk.DISABLED)
            self.btn_delete_crop.configure(state=tk.DISABLED)
            self.title(f"Multi Image Cropper - {os.path.basename(path)}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or process image:\n{e}")
            self.image_path = None
            self.original_image = None
            self.clear_all_crops()
            self.canvas.delete("all")
            self.tk_image = None
            self.display_image = None
            self.btn_save_crops.configure(state=tk.DISABLED)
            self.btn_delete_crop.configure(state=tk.DISABLED)
            self.title("Multi Image Cropper")

    def _fit_image_to_canvas(self):
        """Calculates zoom and offset to fit the image initially."""
        self.update_idletasks() # Ensure canvas dimensions are updated
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width, canvas_height = 600, 500 # Fallback default

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

    def clear_all_crops(self):
        """Clears existing crops, listbox, and resets related states."""
        self.canvas.delete(CROP_RECT_TAG)
        self.canvas.delete(TEMP_RECT_TAG)
        self.crops.clear()
        self.crop_order = []
        self.crop_listbox.delete(0, tk.END)
        self.selected_crop_ids.clear()
        self._update_button_states() # Centralized button state update

    def display_image_on_canvas(self):
        """Displays the current image on the canvas respecting zoom and pan."""
        if not self.original_image:
            self.canvas.delete("all")
            return

        disp_w = max(1, int(self.original_image.width * self.zoom_factor))
        disp_h = max(1, int(self.original_image.height * self.zoom_factor))

        try:
            self.display_image = self.original_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
            self.tk_image = ImageTk.PhotoImage(self.display_image)

            self.canvas.delete("all") # Clear everything

            int_offset_x = int(round(self.canvas_offset_x))
            int_offset_y = int(round(self.canvas_offset_y))

            self.canvas_image_id = self.canvas.create_image(
                int_offset_x, int_offset_y,
                anchor=tk.NW, image=self.tk_image, tags=IMAGE_TAG
            )
            self.redraw_all_crops() # Redraw crops over the new image view

        except Exception as e:
            print(f"Error resizing/displaying image: {e}")
            self.canvas.delete("all")

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
    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        if not self.original_image: return

        img_w, img_h = self.original_image.size
        x1 = max(0, min(x1_img, x2_img, img_w))
        y1 = max(0, min(y1_img, y2_img, img_h))
        x2 = max(0, min(max(x1_img, x2_img), img_w))
        y2 = max(0, min(max(y1_img, y2_img), img_h))

        if (x2 - x1) < MIN_CROP_SIZE or (y2 - y1) < MIN_CROP_SIZE:
            print("Crop too small, ignoring.")
            if self.current_rect_id: self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            return

        coords = (x1, y1, x2, y2)
        crop_id = str(uuid.uuid4())
        crop_name = self._generate_next_crop_name()

        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])
        if cx1 is None: return

        rect_id = self.canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH,
            tags=(RECT_TAG_PREFIX + crop_id, CROP_RECT_TAG)
        )

        self.crops[crop_id] = {'coords': coords, 'name': crop_name, 'rect_id': rect_id}
        self.crop_order.append(crop_id)

        # Add to listbox and select the new item
        self.crop_listbox.insert(tk.END, crop_name)
        self.crop_listbox.selection_clear(0, tk.END)
        last_index = self.crop_listbox.size() - 1
        self.crop_listbox.selection_set(last_index)
        self.crop_listbox.activate(last_index)
        self.crop_listbox.see(last_index)

        self.select_crops_by_ids({crop_id}) # Select the newly added crop
        self._update_button_states()


    def _generate_next_crop_name(self):
        """Generates a default crop name like 'basename_Crop_N', finding the lowest unused N."""
        base_name = "Crop"
        if self.image_path:
            base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        prefix = f"{base_name}_Crop_"

        existing_nums = set()
        for data in self.crops.values():
            if data['name'].startswith(prefix):
                try:
                    num_str = data['name'][len(prefix):]
                    existing_nums.add(int(num_str))
                except ValueError:
                    pass # Ignore names that don't end in a number

        i = 1
        while i in existing_nums:
            i += 1
        return f"{prefix}{i}"

    def select_crops_by_ids(self, crop_ids_to_select):
        """Selects crops by their IDs, updating visuals and listbox."""
        # Deselect previously selected items visually on canvas
        for old_id in self.selected_crop_ids:
            if old_id in self.crops:
                rect_id = self.crops[old_id]['rect_id']
                if self.canvas.winfo_exists() and rect_id in self.canvas.find_all():
                     self.canvas.itemconfig(rect_id, outline=DEFAULT_RECT_COLOR)

        self.selected_crop_ids = set(crop_ids_to_select) # Use set for efficiency

        # Update listbox selection
        self.crop_listbox.selection_clear(0, tk.END)
        indices_to_select = []
        for index, current_id in enumerate(self.crop_order):
            if current_id in self.selected_crop_ids:
                indices_to_select.append(index)
                # Select visually on canvas
                if current_id in self.crops:
                    rect_id = self.crops[current_id]['rect_id']
                    if self.canvas.winfo_exists() and rect_id in self.canvas.find_all():
                        self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR)
                        self.canvas.tag_raise(rect_id) # Bring selected to front

        # Set listbox selection based on found indices
        for index in indices_to_select:
            self.crop_listbox.selection_set(index)
            self.crop_listbox.activate(index) # Make one active for keyboard navigation

        if indices_to_select:
             self.crop_listbox.see(indices_to_select[-1]) # Ensure last selected is visible

        self._update_button_states()


    def _update_button_states(self):
        """Updates the state of buttons based on current conditions."""
        has_selection = bool(self.selected_crop_ids)
        has_crops = bool(self.crops)

        self.btn_delete_crop.configure(state=tk.NORMAL if has_selection else tk.DISABLED)
        self.btn_save_crops.configure(state=tk.NORMAL if has_crops else tk.DISABLED)


    def update_crop_coords(self, crop_id, new_img_coords):
        """Updates the stored original image coordinates, ensures validity."""
        if crop_id not in self.crops or not self.original_image:
            return False

        img_w, img_h = self.original_image.size
        x1, y1, x2, y2 = new_img_coords

        # Clamp to bounds and ensure x1<x2, y1<y2
        final_x1 = max(0, min(x1, x2, img_w))
        final_y1 = max(0, min(y1, y2, img_h))
        final_x2 = max(0, min(max(x1, x2), img_w))
        final_y2 = max(0, min(max(y1, y2), img_h))

        if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE:
            # print("Debug: Crop update rejected due to min size violation")
            return False # Update would violate minimum size

        self.crops[crop_id]['coords'] = (final_x1, final_y1, final_x2, final_y2)
        return True # Update successful


    def redraw_all_crops(self):
        """Redraws all rectangles based on stored coords and current view."""
        if not self.canvas.winfo_exists(): return # Canvas might not be ready
        all_canvas_items = self.canvas.find_withtag(CROP_RECT_TAG) # Get existing crop rects

        existing_rect_ids_on_canvas = {int(item) for item in all_canvas_items}
        current_crop_rect_ids = {data['rect_id'] for data in self.crops.values()}

        # Delete canvas rectangles that no longer correspond to a crop
        ids_to_delete = existing_rect_ids_on_canvas - current_crop_rect_ids
        for rect_id in ids_to_delete:
            self.canvas.delete(rect_id)

        # Update or create rectangles for current crops
        for crop_id, data in self.crops.items():
            img_x1, img_y1, img_x2, img_y2 = data['coords']
            cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1)
            cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)

            if cx1 is None: continue # Skip if coords are invalid

            color = SELECTED_RECT_COLOR if crop_id in self.selected_crop_ids else DEFAULT_RECT_COLOR
            tags_tuple = (RECT_TAG_PREFIX + crop_id, CROP_RECT_TAG)
            rect_id = data['rect_id']

            if rect_id in existing_rect_ids_on_canvas:
                 self.canvas.coords(rect_id, cx1, cy1, cx2, cy2)
                 self.canvas.itemconfig(rect_id, outline=color, tags=tags_tuple)
            else:
                 # If rectangle doesn't exist, recreate it and update stored ID
                 new_rect_id = self.canvas.create_rectangle(
                     cx1, cy1, cx2, cy2,
                     outline=color, width=RECT_WIDTH, tags=tags_tuple
                 )
                 self.crops[crop_id]['rect_id'] = new_rect_id

        # Ensure selected are on top
        for crop_id in self.selected_crop_ids:
            if crop_id in self.crops:
                selected_rect_id = self.crops[crop_id]['rect_id']
                if self.canvas.winfo_exists() and selected_rect_id in self.canvas.find_all():
                     self.canvas.tag_raise(selected_rect_id)


    def delete_selected_crops_event(self, event=None):
        """Handles delete key press."""
        self.delete_selected_crops()

    def delete_selected_crops(self):
        """Deletes the currently selected crop(s). Handles multiple selections."""
        selected_indices = self.crop_listbox.curselection()
        if not selected_indices:
            return

        crop_ids_to_delete = set()
        names_to_delete = [] # Store names to find IDs, as listbox returns indices
        for index in selected_indices:
             name = self.crop_listbox.get(index)
             names_to_delete.append(name)
             # Find the ID - could be slow if many crops, consider index mapping
             found_id = self._get_crop_id_from_name(name)
             if found_id:
                 crop_ids_to_delete.add(found_id)


        if not crop_ids_to_delete:
            return

        # Delete associated data
        for crop_id in crop_ids_to_delete:
            if crop_id in self.crops:
                data = self.crops[crop_id]
                if self.canvas.winfo_exists() and data['rect_id'] in self.canvas.find_all():
                    self.canvas.delete(data['rect_id'])
                del self.crops[crop_id]

            # Remove from order list
            if crop_id in self.crop_order:
                 try: # Use try-except for robustness
                     self.crop_order.remove(crop_id)
                 except ValueError:
                     pass # Should not happen if logic is correct

        # Rebuild the listbox after data manipulation
        self._rebuild_listbox()
        self.selected_crop_ids.clear() # Clear selection state
        self._update_button_states()   # Update button states

    # --- Mouse Event Handlers ---

    def _find_topmost_crop_at(self, canvas_x, canvas_y):
        """Finds the ID of the topmost crop rectangle at given canvas coordinates."""
        search_margin = 2 # Small margin for finding items near the click
        overlapping_items = self.canvas.find_overlapping(
            canvas_x - search_margin, canvas_y - search_margin,
            canvas_x + search_margin, canvas_y + search_margin
        )
        clicked_crop_id = None
        for item_id in reversed(overlapping_items): # Check topmost first
            tags = self.canvas.gettags(item_id)
            if tags and tags[0].startswith(RECT_TAG_PREFIX) and CROP_RECT_TAG in tags:
                crop_id = tags[0][len(RECT_TAG_PREFIX):]
                if crop_id in self.crops:
                    return crop_id
        return None

    def on_canvas_left_press(self, event):
        self.canvas.focus_set()
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        clicked_crop_id = self._find_topmost_crop_at(canvas_x, canvas_y)

        # Check if clicking on a resize handle of a *selected* crop
        if len(self.selected_crop_ids) == 1: # Only resize one selected crop
             single_selected_id = list(self.selected_crop_ids)[0]
             handle = self.get_resize_handle(canvas_x, canvas_y, single_selected_id)
             if handle:
                 self.is_resizing = True
                 self.is_moving = False
                 self.is_drawing = False
                 self.resize_handle = handle
                 self.resize_crop_id = single_selected_id
                 self.start_x = canvas_x
                 self.start_y = canvas_y
                 self.resize_start_coords_img = self.crops[self.resize_crop_id]['coords']
                 # print(f"Start resize {handle} on {self.resize_crop_id}")
                 return

        # Check if clicking inside an existing crop to select/move
        if clicked_crop_id:
            # Handle selection modifiers (Shift/Ctrl) - Simplified for now: Just select clicked
            # Proper multi-select dragging needs more state (which item initiated move)
            if clicked_crop_id not in self.selected_crop_ids:
                self.select_crops_by_ids({clicked_crop_id}) # Select only the clicked one

            if self.selected_crop_ids: # Proceed only if something is now selected
                 self.is_moving = True
                 self.is_drawing = False
                 self.is_resizing = False
                 self.start_x = canvas_x
                 self.start_y = canvas_y

                 # Calculate offset from click point to top-left of the *clicked* rectangle
                 rect_coords = self.canvas.coords(self.crops[clicked_crop_id]['rect_id'])
                 self.move_offset_x = canvas_x - rect_coords[0]
                 self.move_offset_y = canvas_y - rect_coords[1]

                 # Store starting image coords for *all* selected rectangles for delta calculation
                 self.move_selection_start_coords = {}
                 for sel_id in self.selected_crop_ids:
                    self.move_selection_start_coords[sel_id] = self.crops[sel_id]['coords']

                 # print(f"Start moving selection: {self.selected_crop_ids}")
                 return

        # If not clicking handle or existing rect, start drawing
        if self.original_image:
            self.is_drawing = True
            self.is_moving = False
            self.is_resizing = False
            self.start_x = canvas_x
            self.start_y = canvas_y
            self.current_rect_id = self.canvas.create_rectangle(
                self.start_x, self.start_y, self.start_x, self.start_y,
                outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4),
                tags=(TEMP_RECT_TAG,)
            )
            # Deselect any currently selected crop when starting to draw new one
            self.select_crops_by_ids(set())


    def on_canvas_right_click(self, event):
         """Handles right-click to select a crop for editing."""
         self.canvas.focus_set()
         canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
         clicked_crop_id = self._find_topmost_crop_at(canvas_x, canvas_y)

         if clicked_crop_id:
             # Select only the right-clicked crop
             self.select_crops_by_ids({clicked_crop_id})
             self.is_moving = False # Don't start moving on right click
             self.is_drawing = False
             self.is_resizing = False
             self.update_cursor(event) # Update cursor immediately
             # print(f"Right-clicked and selected: {clicked_crop_id}")
         else:
             # Right-click on empty space could potentially deselect, but let's keep selection for now.
             pass

    def on_canvas_left_drag(self, event):
        if not self.canvas.winfo_exists(): return
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.is_drawing and self.current_rect_id:
            self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)

        elif self.is_moving and self.selected_crop_ids:
             # Calculate drag distance on canvas
             dx_canvas = canvas_x - self.start_x
             dy_canvas = canvas_y - self.start_y

             # Apply move to all selected rectangles
             for crop_id in self.selected_crop_ids:
                if crop_id in self.move_selection_start_coords and crop_id in self.crops:
                    # Get starting canvas coords for *this* crop (for validation)
                    start_img_coords = self.move_selection_start_coords[crop_id]
                    start_cx1, start_cy1 = self.image_to_canvas_coords(start_img_coords[0], start_img_coords[1])
                    start_cx2, start_cy2 = self.image_to_canvas_coords(start_img_coords[2], start_img_coords[3])

                    if start_cx1 is None: continue # Skip if coord conversion failed

                    # Calculate new desired canvas top-left for this crop
                    new_cx1 = start_cx1 + dx_canvas
                    new_cy1 = start_cy1 + dy_canvas

                    # Convert *target* canvas top-left to image coords
                    new_img_x1, new_img_y1 = self.canvas_to_image_coords(new_cx1, new_cy1)

                    if new_img_x1 is not None:
                         # Calculate new img bottom-right based on original size (avoids zoom drift)
                         img_w = start_img_coords[2] - start_img_coords[0]
                         img_h = start_img_coords[3] - start_img_coords[1]
                         new_img_x2 = new_img_x1 + img_w
                         new_img_y2 = new_img_y1 + img_h

                         # Update stored coordinates (validates bounds & min size)
                         updated = self.update_crop_coords(crop_id, (new_img_x1, new_img_y1, new_img_x2, new_img_y2))
                         if updated:
                             # If stored coords updated, redraw the rect on canvas from stored coords
                             validated_img_coords = self.crops[crop_id]['coords']
                             cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                             cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                             if cx1_final is not None:
                                  self.canvas.coords(self.crops[crop_id]['rect_id'], cx1_final, cy1_final, cx2_final, cy2_final)

        elif self.is_resizing and self.resize_crop_id and self.resize_handle:
            crop_id = self.resize_crop_id
            rect_id = self.crops[crop_id]['rect_id']

            # Use stored original coords as base
            ox1_img, oy1_img, ox2_img, oy2_img = self.resize_start_coords_img

            # Convert current mouse canvas coords to image coords
            curr_img_x, curr_img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            # Convert starting mouse canvas coords to image coords (where resize grab started)
            start_img_x, start_img_y = self.canvas_to_image_coords(self.start_x, self.start_y)

            if curr_img_x is None or start_img_x is None: return

            # Delta in image coords (how much mouse moved in image space)
            # Use the clamped start coords if they are valid, else use original
            if start_img_x is not None:
                start_img_x_clamped = max(0, min(start_img_x, self.original_image.width))
                start_img_y_clamped = max(0, min(start_img_y, self.original_image.height))
            else:
                # Fallback - should not happen if resize started correctly
                start_img_x_clamped, start_img_y_clamped = ox1_img, oy1_img

            # Calculate clamped current mouse position in image coordinates
            curr_img_x_clamped = max(0, min(curr_img_x, self.original_image.width))
            curr_img_y_clamped = max(0, min(curr_img_y, self.original_image.height))

            dx_img = curr_img_x_clamped - start_img_x_clamped
            dy_img = curr_img_y_clamped - start_img_y_clamped

            # Adjust coordinates based on handle
            nx1, ny1, nx2, ny2 = ox1_img, oy1_img, ox2_img, oy2_img
            if 'n' in self.resize_handle: ny1 += dy_img
            if 's' in self.resize_handle: ny2 += dy_img
            if 'w' in self.resize_handle: nx1 += dx_img
            if 'e' in self.resize_handle: nx2 += dx_img

            # Update stored coords (validates min size, bounds, order x1<x2)
            updated = self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2))
            if updated:
                 validated_img_coords = self.crops[crop_id]['coords']
                 cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                 cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                 if cx1_final is not None:
                    self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)

    def on_canvas_left_release(self, event):
        if self.is_drawing and self.current_rect_id:
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            if self.canvas.winfo_exists() and self.current_rect_id in self.canvas.find_withtag(TEMP_RECT_TAG):
                self.canvas.delete(self.current_rect_id)

            img_x1, img_y1 = self.canvas_to_image_coords(self.start_x, self.start_y)
            img_x2, img_y2 = self.canvas_to_image_coords(canvas_x, canvas_y)

            if img_x1 is not None and img_x2 is not None:
                 self.add_crop(img_x1, img_y1, img_x2, img_y2)
            else:
                 print("Failed to add crop due to coordinate conversion error.")

        # Reset states
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.resize_crop_id = None
        self.current_rect_id = None
        self.move_selection_start_coords = {}
        self.start_x = None
        self.start_y = None

        self.update_cursor(event) # Update cursor based on final position

    # --- Zoom and Pan Handlers ---
    def on_mouse_wheel(self, event, direction=None):
        if not self.original_image or not self.canvas.winfo_exists(): return

        if direction: delta = direction # Linux explicit direction
        elif event.num == 5 or event.delta < 0: delta = -1 # Scroll down/out
        elif event.num == 4 or event.delta > 0: delta = 1 # Scroll up/in
        else: return

        zoom_increment = 1.1
        min_zoom = 0.01
        max_zoom = 20.0

        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)

        img_x_before, img_y_before = self.canvas_to_image_coords(canvas_x, canvas_y)
        if img_x_before is None: return

        if delta > 0: new_zoom = self.zoom_factor * zoom_increment
        else: new_zoom = self.zoom_factor / zoom_increment
        new_zoom = max(min_zoom, min(max_zoom, new_zoom))

        if new_zoom == self.zoom_factor: return

        self.zoom_factor = new_zoom

        # Keep point under mouse stationary
        self.canvas_offset_x = canvas_x - (img_x_before * self.zoom_factor)
        self.canvas_offset_y = canvas_y - (img_y_before * self.zoom_factor)

        self.display_image_on_canvas() # Redraw image and crops at new scale/offset

    def on_pan_press(self, event):
        if not self.original_image: return
        self.is_panning = True
        self.pan_start_x = self.canvas.canvasx(event.x)
        self.pan_start_y = self.canvas.canvasy(event.y)
        self.canvas.config(cursor="fleur")

    def on_pan_drag(self, event):
        if not self.is_panning or not self.original_image or not self.canvas.winfo_exists(): return
        current_x = self.canvas.canvasx(event.x)
        current_y = self.canvas.canvasy(event.y)
        dx = current_x - self.pan_start_x
        dy = current_y - self.pan_start_y

        self.canvas_offset_x += dx
        self.canvas_offset_y += dy
        self.canvas.move("all", dx, dy) # Move all canvas items visually

        self.pan_start_x = current_x
        self.pan_start_y = current_y

    def on_pan_release(self, event):
        self.is_panning = False
        self.update_cursor(event) # Reset cursor based on current position


    # --- Listbox Event Handlers ---
    def on_listbox_select(self, event=None):
         """Handles selection changes in the listbox."""
         if not self.crop_listbox.winfo_exists(): return

         selected_indices = self.crop_listbox.curselection()
         selected_ids_from_listbox = set()

         if selected_indices:
             for index in selected_indices:
                 try:
                    crop_id = self._get_crop_id_from_list_index(index)
                    if crop_id:
                        selected_ids_from_listbox.add(crop_id)
                 except IndexError:
                     print(f"Warning: Listbox index {index} out of sync with crop_order.")
                     # Attempt to rebuild listbox might be needed if out of sync badly
                     # self._rebuild_listbox()
                     # return # Avoid further processing on inconsistent state
         # print(f"Listbox selection changed. Indices: {selected_indices}, IDs: {selected_ids_from_listbox}")

         # Only update if the listbox selection differs from the internal state
         # Prevents infinite loops if selection is set programmatically
         if selected_ids_from_listbox != self.selected_crop_ids:
              self.select_crops_by_ids(selected_ids_from_listbox)


    def on_listbox_drag_start(self, event):
        self.drag_start_index = self.crop_listbox.nearest(event.y)
        # print(f"Drag start: {self.drag_start_index}")

    def on_listbox_drag_motion(self, event):
        if self.drag_start_index is None: return # Drag didn't start on an item
        current_index = self.crop_listbox.nearest(event.y)
        if current_index != self.drag_drop_index:
             self.drag_drop_index = current_index
             self.crop_listbox.activate(current_index) # Visual feedback for drop target
             # print(f"Dragging over: {current_index}")

    def on_listbox_drag_release(self, event):
        if self.drag_start_index is not None and self.drag_drop_index is not None and self.drag_start_index != self.drag_drop_index:
            if 0 <= self.drag_start_index < len(self.crop_order) and 0 <= self.drag_drop_index < len(self.crop_order):

                 # print(f"Drop attempt: move index {self.drag_start_index} to {self.drag_drop_index}")

                 # Perform the reorder in self.crop_order
                 moved_id = self.crop_order.pop(self.drag_start_index)
                 # Adjust drop index if item was removed from before the drop target
                 actual_drop_index = self.drag_drop_index
                 if self.drag_start_index < self.drag_drop_index:
                       # Item removed from before the target, drop target index effectively decreases by 1
                       # No, the insertion point index remains the same.
                       pass # No index adjustment needed here when inserting

                 self.crop_order.insert(actual_drop_index, moved_id)

                 # Rebuild the listbox to reflect the new order
                 selected_ids_before_rebuild = {moved_id} # Keep the moved item selected
                 self._rebuild_listbox(select_ids=selected_ids_before_rebuild)
                 # print(f"Drop successful. New order: {self.crop_order}")
            # else:
                 # print(f"Drop cancelled: Invalid indices ({self.drag_start_index}, {self.drag_drop_index}), Order Length: {len(self.crop_order)}")


        # Reset drag state regardless of success
        self.drag_start_index = None
        self.drag_drop_index = None
        # Trigger a regular selection update to ensure consistency
        self.on_listbox_select()

    def on_listbox_double_click(self, event):
        """Handles renaming a crop on double-click."""
        selected_indices = self.crop_listbox.curselection()
        if len(selected_indices) != 1: return # Only rename single selection

        index = selected_indices[0]
        crop_id = self._get_crop_id_from_list_index(index)

        if crop_id and crop_id in self.crops:
             current_name = self.crops[crop_id]['name']
             dialog = ctk.CTkInputDialog(text="Enter new name:", title="Rename Crop",)
             # Position dialog near the listbox (optional, needs coordinate mapping)
             # x = self.control_frame.winfo_rootx() + 50
             # y = self.control_frame.winfo_rooty() + self.crop_listbox.winfo_y() + (index * 20) # Approximate position
             # dialog.geometry(f"+{x}+{y}")
             new_name = dialog.get_input()


             if new_name and new_name != current_name:
                  # Optional: Check for duplicate names
                  is_duplicate = any(data['name'] == new_name for cid, data in self.crops.items() if cid != crop_id)
                  if is_duplicate:
                      messagebox.showwarning("Duplicate Name", "Another crop already has this name. Please choose a different name.")
                      return

                  # Update internal data
                  self.crops[crop_id]['name'] = new_name
                  # Update listbox item directly
                  self.crop_listbox.delete(index)
                  self.crop_listbox.insert(index, new_name)
                  # Reselect the renamed item
                  self.crop_listbox.selection_set(index)
                  self.crop_listbox.activate(index)
                  self.select_crops_by_ids({crop_id}) # Update internal selection state


    # --- Helper Functions ---

    def _rebuild_listbox(self, select_ids=None):
        """Clears and repopulates the listbox from self.crop_order."""
        if not self.crop_listbox.winfo_exists(): return
        if select_ids is None: # Remember selection if not specified
             select_ids = self.selected_crop_ids.copy()

        self.crop_listbox.delete(0, tk.END)
        new_indices_to_select = []
        for i, crop_id in enumerate(self.crop_order):
            if crop_id in self.crops:
                name = self.crops[crop_id]['name']
                self.crop_listbox.insert(tk.END, name)
                if crop_id in select_ids:
                    new_indices_to_select.append(i)
            else:
                print(f"Warning: Crop ID {crop_id} found in order list but not in crops dict during rebuild.")

        # Restore selection
        if new_indices_to_select:
             for index in new_indices_to_select:
                 self.crop_listbox.selection_set(index)
             self.crop_listbox.activate(new_indices_to_select[-1])
             self.crop_listbox.see(new_indices_to_select[-1])

        # Important: Sync internal selection state after rebuild
        self.selected_crop_ids = set(select_ids) if select_ids else set()
        self._update_button_states()


    def _get_crop_id_from_list_index(self, index):
         """Safely gets the crop ID corresponding to a listbox index using crop_order."""
         try:
             return self.crop_order[index]
         except IndexError:
             print(f"Error: Index {index} out of range for crop_order (length {len(self.crop_order)}).")
             return None

    def _get_crop_id_from_name(self, name):
        """Finds the crop ID based on its name."""
        for crop_id, data in self.crops.items():
            if data['name'] == name:
                return crop_id
        print(f"Warning: Could not find crop ID for name '{name}'.")
        return None

    # --- Resizing Helpers ---
    def get_resize_handle(self, canvas_x, canvas_y, crop_id_to_check):
        """Checks if the cursor is near a resize handle of the specified crop."""
        if not crop_id_to_check or crop_id_to_check not in self.crops or not self.canvas.winfo_exists():
            return None

        rect_id = self.crops[crop_id_to_check]['rect_id']
        if rect_id not in self.canvas.find_all():
             return None

        try:
            cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
        except tk.TclError: # Handle cases where coords might be invalid temporarily
            return None

        handle_margin = 6 # Pixel proximity

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
        if not self.canvas.winfo_exists(): return

        new_cursor = "" # Default cursor

        if self.is_panning or (self.is_moving and self.selected_crop_ids):
             new_cursor = "fleur"
        elif self.is_resizing: # Determine resize cursor based on handle
             handle = self.resize_handle
             if handle in ('nw', 'se'): new_cursor = "size_nw_se"
             elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
             elif handle in ('n', 's'): new_cursor = "size_ns"
             elif handle in ('e', 'w'): new_cursor = "size_we"
        elif event: # Not actively dragging, check hover state
             canvas_x = self.canvas.canvasx(event.x)
             canvas_y = self.canvas.canvasy(event.y)

             resize_handle_found = None
             hover_crop_id = None
             # Only show resize handles if exactly one crop is selected
             if len(self.selected_crop_ids) == 1:
                 single_selected_id = list(self.selected_crop_ids)[0]
                 resize_handle_found = self.get_resize_handle(canvas_x, canvas_y, single_selected_id)
                 if resize_handle_found:
                      hover_crop_id = single_selected_id # We are hovering handle of selected item

             if resize_handle_found:
                 handle = resize_handle_found
                 if handle in ('nw', 'se'): new_cursor = "size_nw_se"
                 elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
                 elif handle in ('n', 's'): new_cursor = "size_ns"
                 elif handle in ('e', 'w'): new_cursor = "size_we"
             else:
                 # Check if hovering *inside* any selected rectangle
                 is_over_selected = False
                 for crop_id in self.selected_crop_ids:
                     if crop_id in self.crops:
                        rect_id = self.crops[crop_id]['rect_id']
                        if self.canvas.winfo_exists() and rect_id in self.canvas.find_all():
                           try:
                                cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
                                if cx1 < canvas_x < cx2 and cy1 < canvas_y < cy2:
                                     is_over_selected = True
                                     break
                           except tk.TclError: pass # Ignore if coords invalid

                 if is_over_selected:
                    new_cursor = "fleur" # Movable cursor

        if self.canvas.cget("cursor") != new_cursor:
            self.canvas.config(cursor=new_cursor)


    # --- Window Resize Handling ---
    def on_window_resize(self, event=None):
        # Can optionally trigger image refit here, but might be jarring.
        # For now, just let Tk handle widget resizing.
        # self.display_image_on_canvas() # Re-render potentially needed if quality degrades
        pass

    # --- Saving Crops ---
    def save_crops(self):
        if not self.original_image or not self.image_path:
            messagebox.showwarning("No Image", "Please select an image first.")
            return
        if not self.crop_order: # Check order list instead of crops dict directly
            messagebox.showwarning("No Crops", "Please define at least one crop area.")
            return

        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        # Save in a subdirectory named after the image, located where the script/exe is.
        output_dir = os.path.abspath(base_name)

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Directory Error", f"Could not create output directory:\n{output_dir}\n{e}")
            return

        saved_count = 0
        error_count = 0

        # ** Save crops based on the order in self.crop_order **
        for i, crop_id in enumerate(self.crop_order):
            if crop_id in self.crops:
                data = self.crops[crop_id]
                coords = tuple(map(int, data['coords'])) # Ensure integer coords

                # Save using sequential naming based on list order
                filename = f"{base_name}_{i + 1}.jpg" # e.g., MyImage_1.jpg, MyImage_2.jpg
                filepath = os.path.join(output_dir, filename)

                try:
                    cropped_img = self.original_image.crop(coords)
                    # Convert to RGB if necessary (e.g., for RGBA PNGs or indexed GIF)
                    if cropped_img.mode in ('RGBA', 'P'):
                        cropped_img = cropped_img.convert('RGB')
                    cropped_img.save(filepath, "JPEG", quality=95)
                    saved_count += 1
                except Exception as e:
                    error_count += 1
                    print(f"Error saving crop '{data['name']}' to {filename}: {e}")
            else:
                 error_count += 1
                 print(f"Error: Crop ID {crop_id} from order list not found in crops dictionary during save.")


        if error_count == 0:
            messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to the '{base_name}' folder.")
        else:
            messagebox.showwarning("Partial Success", f"Saved {saved_count} crops to '{base_name}'.\nFailed to save {error_count} crops. Check console/log for details.")


# --- Run the Application ---
if __name__ == "__main__":
    # Make sure PIL Image references aren't garbage collected early in callbacks
    # (Shouldn't be an issue with how tk_image is stored on self, but good practice)
    from PIL import Image
    Image.init()

    app = MultiCropApp()
    app.mainloop()
