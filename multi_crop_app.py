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
        self.title("Multi Image Cropper (Improved v2)")
        self.geometry("1150x750") # Slightly wider for move buttons
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
        self.used_crop_numbers = set() # Tracks numbers used in default names
        self.selected_crop_ids = [] # List of selected crop_ids (for multi-delete, canvas highlight)

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
        # Added state to prevent double-click interference
        self._after_id_single_click = None
        self._double_click_pending = False


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
        self.control_frame.grid_rowconfigure(4, weight=1) # Listbox frame takes expansion
        self.control_frame.grid_columnconfigure(0, weight=1) # Column for main controls
        self.control_frame.grid_columnconfigure(1, weight=0) # Column for move buttons

        # Buttons (Main)
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image", command=self.select_image)
        self.btn_select_image.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew") # Span both columns

        self.btn_save_crops = ctk.CTkButton(self.control_frame, text="Save All Crops", command=self.save_crops, state=tk.DISABLED)
        self.btn_save_crops.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

        # Crop List Label
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List (Double-Click to Rename):")
        self.lbl_crop_list.grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w")

        # Listbox Frame (holds listbox and scrollbar)
        self.listbox_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.listbox_frame.grid(row=3, column=0, padx=(10,0), pady=5, sticky="nsew") # Pad right 0
        self.listbox_frame.grid_rowconfigure(0, weight=1)
        self.listbox_frame.grid_columnconfigure(0, weight=1)

        # Listbox Scrollbar
        self.listbox_scrollbar = ctk.CTkScrollbar(self.listbox_frame, command=None)
        self.listbox_scrollbar.grid(row=0, column=1, sticky="ns")

        # Crop Listbox
        self.crop_listbox = Listbox(self.listbox_frame,
                                    bg='white', fg='black',
                                    selectbackground='#ADD8E6',
                                    selectforeground='black',
                                    highlightthickness=1, highlightbackground="#CCCCCC",
                                    highlightcolor="#89C4F4",
                                    borderwidth=0, exportselection=False,
                                    selectmode=tk.EXTENDED, # Multi-select enabled
                                    yscrollcommand=self.listbox_scrollbar.set)
        self.crop_listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox_scrollbar.configure(command=self.crop_listbox.yview)

        # --- Move Up/Down Buttons ---
        self.move_button_frame = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.move_button_frame.grid(row=3, column=1, padx=(5, 10), pady=5, sticky="ns") # Place next to listbox frame

        self.btn_move_up = ctk.CTkButton(self.move_button_frame, text="↑", width=30, command=self.move_selected_item_up, state=tk.DISABLED)
        self.btn_move_up.pack(pady=(0, 5), padx=0)

        self.btn_move_down = ctk.CTkButton(self.move_button_frame, text="↓", width=30, command=self.move_selected_item_down, state=tk.DISABLED)
        self.btn_move_down.pack(pady=(5, 0), padx=0)
        # --- End Move Buttons ---


        # Delete Button (Back under the listbox area, spanning columns)
        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete Selected Crop(s)", command=self.delete_selected_crops, state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crop.grid(row=4, column=0, columnspan=2, padx=10, pady=(5, 10), sticky="sew") # Stick bottom, span

        # --- Bindings ---
        # Canvas Bindings (Modified Click/Double-Click)
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press) # Handles single click logic start
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release) # Handles single click logic end
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click) # Handles double click action
        # Other Canvas Bindings
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1))
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1))
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press)
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.update_cursor)

        # Listbox Bindings
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.crop_listbox.bind("<Double-Button-1>", self.on_listbox_double_click) # Rename
        # Removed listbox drag bindings

        # Global Key Bindings
        self.bind("<Delete>", self.delete_selected_crops_event)
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
                canvas_width, canvas_height = 600, 500

            img_width, img_height = self.original_image.size
            if img_width <= 0 or img_height <= 0:
                 raise ValueError("Image has zero or negative dimension")

            zoom_h = canvas_width / img_width
            zoom_v = canvas_height / img_height
            initial_zoom = min(zoom_h, zoom_v)
            padding_factor = 0.98
            self.zoom_factor = min(1.0, initial_zoom) * padding_factor

            display_w = img_width * self.zoom_factor
            display_h = img_height * self.zoom_factor
            self.canvas_offset_x = math.ceil((canvas_width - display_w) / 2)
            self.canvas_offset_y = math.ceil((canvas_height - display_h) / 2)

            self.clear_all_crops()
            self.display_image_on_canvas()
            self.update_button_states() # Ensure buttons are correctly disabled initially

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or process image:\n{e}")
            self.image_path = None
            self.original_image = None
            self.clear_all_crops()
            self.canvas.delete("all")
            self.tk_image = None
            self.display_image = None
            self.update_button_states()


    def clear_all_crops(self):
        """Clears all crop data, listbox, order, numbers, and selection."""
        self.canvas.delete("crop_rect")
        self.crops.clear()
        self.crop_order = []
        self.used_crop_numbers = set()
        self.selected_crop_ids = []
        self.crop_listbox.delete(0, tk.END)
        # Cancel any pending single click action
        if self._after_id_single_click:
            self.after_cancel(self._after_id_single_click)
            self._after_id_single_click = None
        self._double_click_pending = False
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
        self.canvas.delete("all")
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
    def find_available_crop_number(self):
        i = 1
        while i in self.used_crop_numbers: i += 1
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
            if self.current_rect_id and self.current_rect_id in self.canvas.find_all():
                 self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            return

        coords = (min(x1_img, x2_img), min(y1_img, y2_img),
                  max(x1_img, x2_img), max(y1_img, y2_img))

        crop_id = str(uuid.uuid4())
        crop_number = self.find_available_crop_number()
        self.used_crop_numbers.add(crop_number)

        base_name = os.path.splitext(os.path.basename(self.image_path))[0] if self.image_path else "Image"
        crop_name = f"{base_name}_Crop_{crop_number}"

        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])

        if cx1 is None:
            print("Error: Cannot draw crop, coordinate conversion failed.")
            self.used_crop_numbers.discard(crop_number) # Rollback
            return

        rect_id = self.canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH,
            tags=(RECT_TAG_PREFIX + crop_id, "crop_rect")
        )

        self.crops[crop_id] = {'coords': coords, 'name': crop_name, 'rect_id': rect_id}
        self.crop_order.append(crop_id)

        self.rebuild_listbox()
        new_index = self.get_list_index_from_crop_id(crop_id)
        if new_index != -1:
            self.crop_listbox.selection_clear(0, tk.END)
            self.crop_listbox.selection_set(new_index)
            self.on_listbox_select() # Trigger selection logic for buttons etc.

        self.update_button_states()


    def get_crop_id_from_list_index(self, index):
        if 0 <= index < len(self.crop_order):
            return self.crop_order[index]
        return None

    def get_list_index_from_crop_id(self, crop_id):
        try:
            return self.crop_order.index(crop_id)
        except ValueError:
            return -1

    def select_crops(self, crop_ids_to_select, source="unknown"):
        """Selects one or more crops by ID, updating visuals. Source helps debugging."""
        # print(f"Select_crops called from {source} with IDs: {crop_ids_to_select}") # Debug
        new_selection = list(crop_ids_to_select) # Make a copy

        # Only update if the selection has actually changed
        if set(self.selected_crop_ids) == set(new_selection):
            # print("Selection unchanged, returning.") # Debug
            return

        # Deselect previously selected crops visually
        ids_to_deselect = set(self.selected_crop_ids) - set(new_selection)
        for prev_id in ids_to_deselect:
            if prev_id in self.crops:
                rect_id = self.crops[prev_id].get('rect_id')
                if rect_id and rect_id in self.canvas.find_all():
                     try:
                         self.canvas.itemconfig(rect_id, outline=DEFAULT_RECT_COLOR)
                     except tk.TclError as e:
                         print(f"Warning: TclError deselecting {rect_id}: {e}")


        self.selected_crop_ids = new_selection

        # Select new ones visually
        ids_to_select = set(new_selection) - (set(self.selected_crop_ids) - set(new_selection)) # IDs newly added
        for crop_id in self.selected_crop_ids: # Iterate over the final selection
            if crop_id in self.crops:
                rect_id = self.crops[crop_id].get('rect_id')
                if rect_id and rect_id in self.canvas.find_all():
                    try:
                        self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR)
                        self.canvas.tag_raise(rect_id)
                    except tk.TclError as e:
                         print(f"Warning: TclError selecting/raising {rect_id}: {e}")
                elif rect_id:
                     print(f"Warning: Stale rectangle ID {rect_id} for crop {crop_id}")
            else:
                 print(f"Warning: Attempted to select non-existent crop ID {crop_id}")


        self.update_button_states()

        # Update listbox selection unless the call came from the listbox itself
        if source != "listbox":
            # print("Updating listbox visuals") # Debug
            self.update_listbox_selection_visuals()


    def update_crop_coords(self, crop_id, new_img_coords):
        if crop_id in self.crops and self.original_image:
             img_w, img_h = self.original_image.size
             x1, y1, x2, y2 = new_img_coords
             x1 = max(0, min(x1, img_w)); y1 = max(0, min(y1, img_h))
             x2 = max(0, min(x2, img_w)); y2 = max(0, min(y2, img_h))
             final_x1 = min(x1, x2); final_y1 = min(y1, y2)
             final_x2 = max(x1, x2); final_y2 = max(y1, y2)

             if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE:
                 return False

             self.crops[crop_id]['coords'] = (final_x1, final_y1, final_x2, final_y2)
             return True
        return False


    def redraw_all_crops(self):
        """Redraws all rectangles based on stored coords, order, and current view."""
        all_canvas_items_ids = set(self.canvas.find_all()) # Efficient lookup

        for crop_id in self.crop_order:
            if crop_id not in self.crops: continue
            data = self.crops[crop_id]
            img_x1, img_y1, img_x2, img_y2 = data['coords']
            cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1)
            cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)

            if cx1 is None: continue

            color = SELECTED_RECT_COLOR if crop_id in self.selected_crop_ids else DEFAULT_RECT_COLOR
            tags_tuple = (RECT_TAG_PREFIX + crop_id, "crop_rect")
            rect_id = data.get('rect_id')

            try:
                if rect_id and rect_id in all_canvas_items_ids:
                    self.canvas.coords(rect_id, cx1, cy1, cx2, cy2)
                    self.canvas.itemconfig(rect_id, outline=color, tags=tags_tuple)
                else:
                    new_rect_id = self.canvas.create_rectangle(
                        cx1, cy1, cx2, cy2,
                        outline=color, width=RECT_WIDTH, tags=tags_tuple
                    )
                    self.crops[crop_id]['rect_id'] = new_rect_id # Update stored ID
                    rect_id = new_rect_id # Use the new ID for raising if selected

                # Raise if selected
                if crop_id in self.selected_crop_ids and rect_id:
                    self.canvas.tag_raise(rect_id)

            except tk.TclError as e:
                print(f"Error drawing/updating rect for {crop_id} (ID: {rect_id}): {e}")
                # Attempt to remove potentially bad ID?
                if rect_id and 'rect_id' in self.crops[crop_id]:
                    del self.crops[crop_id]['rect_id']


    def delete_selected_crops_event(self, event=None):
        self.delete_selected_crops()

    def delete_selected_crops(self):
        ids_to_delete = list(self.selected_crop_ids) # Use the current selection state
        if not ids_to_delete:
            # Fallback: check listbox selection if internal state is empty (shouldn't happen often)
            indices_to_delete = self.crop_listbox.curselection()
            if not indices_to_delete: return
            ids_to_delete = [self.get_crop_id_from_list_index(i) for i in indices_to_delete]
            ids_to_delete = [id for id in ids_to_delete if id] # Filter out None

        if not ids_to_delete: return

        deleted_count = 0
        for crop_id in ids_to_delete:
            if crop_id in self.crops:
                data = self.crops[crop_id]
                try:
                    parts = data['name'].split('_')
                    if len(parts) > 1 and parts[-1].isdigit():
                        num = int(parts[-1])
                        self.used_crop_numbers.discard(num)
                except (ValueError, IndexError):
                     print(f"Could not parse number from crop name: {data['name']}")

                rect_id = data.get('rect_id')
                if rect_id and rect_id in self.canvas.find_all():
                    try:
                        self.canvas.delete(rect_id)
                    except tk.TclError as e:
                         print(f"Warning: TclError deleting rect {rect_id}: {e}")

                del self.crops[crop_id]
                deleted_count += 1

        self.crop_order = [id for id in self.crop_order if id not in ids_to_delete]
        self.selected_crop_ids = [] # Clear selection
        self.rebuild_listbox()
        print(f"Deleted {deleted_count} crop(s).")
        self.update_button_states()


    def rebuild_listbox(self):
        """Clears and repopulates the listbox based on self.crop_order."""
        # print("Rebuilding listbox") # Debug
        current_selection = self.crop_listbox.curselection() # Remember selection if needed
        self.crop_listbox.delete(0, tk.END)
        for crop_id in self.crop_order:
            if crop_id in self.crops:
                self.crop_listbox.insert(tk.END, self.crops[crop_id]['name'])
            else:
                print(f"Warning: crop_id {crop_id} in order but not in crops dict during rebuild.")
        # Restore selection might be needed depending on the operation
        # self.update_listbox_selection_visuals() # Let the calling context handle reselection


    def update_button_states(self):
        """ Enable/disable buttons based on current state. """
        has_crops = bool(self.crops)
        num_selected = len(self.selected_crop_ids)
        listbox_selection_indices = self.crop_listbox.curselection() # Check listbox directly for move buttons
        listbox_num_selected = len(listbox_selection_indices)


        self.btn_save_crops.configure(state=tk.NORMAL if has_crops else tk.DISABLED)
        self.btn_delete_crop.configure(state=tk.NORMAL if num_selected > 0 else tk.DISABLED)

        # Move buttons require exactly one listbox selection
        can_move_up = False
        can_move_down = False
        if listbox_num_selected == 1:
            selected_index = listbox_selection_indices[0]
            if selected_index > 0:
                can_move_up = True
            if selected_index < self.crop_listbox.size() - 1:
                can_move_down = True

        self.btn_move_up.configure(state=tk.NORMAL if can_move_up else tk.DISABLED)
        self.btn_move_down.configure(state=tk.NORMAL if can_move_down else tk.DISABLED)


    # --- Mouse Event Handlers (Canvas) ---

    def on_mouse_press(self, event):
        """ Handle Button-1 press: Initiate potential drag/draw or schedule single-click action. """
        self.canvas.focus_set()
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # Cancel any pending single click from previous press
        if self._after_id_single_click:
            self.after_cancel(self._after_id_single_click)
            self._after_id_single_click = None

        self._double_click_pending = True # Assume double-click until proven otherwise by release timing

        # Identify item under cursor
        self.start_x, self.start_y = canvas_x, canvas_y
        item_id = self.find_topmost_crop_rect(canvas_x, canvas_y)
        handle = None
        clicked_crop_id = None

        if item_id:
             tags = self.canvas.gettags(item_id)
             if tags and tags[0].startswith(RECT_TAG_PREFIX):
                  clicked_crop_id = tags[0][len(RECT_TAG_PREFIX):]

        # Check for resize handle if exactly one item is selected *and* we clicked on it
        if len(self.selected_crop_ids) == 1 and clicked_crop_id == self.selected_crop_ids[0]:
             handle = self.get_resize_handle(canvas_x, canvas_y, clicked_crop_id)

        if handle:
            self.is_resizing = True
            self.resize_handle = handle
            self.start_coords_img = self.crops[clicked_crop_id]['coords']
            self._double_click_pending = False # Cannot be double-click if starting resize
            # print("Starting resize") # Debug
        elif clicked_crop_id:
            # Clicked on an existing rectangle
            # Prepare for potential move, but don't select yet (wait for release or double-click)
            self.is_moving = False # Set to true only on drag
            rect_coords = self.canvas.coords(item_id)
            self.move_offset_x = canvas_x - rect_coords[0]
            self.move_offset_y = canvas_y - rect_coords[1]
            # print(f"Clicked on potential move item: {clicked_crop_id}") # Debug
        else:
            # Clicked on empty space, prepare for drawing
            self.is_drawing = True
            self.current_rect_id = None # Created on drag
            self._double_click_pending = False # Cannot be double-click if starting draw
            # print("Starting potential draw") # Debug


    def handle_single_click_action(self, event):
        """ Performs the action for a single click after a delay. """
        # print("Executing single click action") # Debug
        self._after_id_single_click = None # Clear the timer ID
        if self._double_click_pending: # Should be false if double click happened
            self._double_click_pending = False # Ensure it's false now

            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            item_id = self.find_topmost_crop_rect(canvas_x, canvas_y)
            clicked_crop_id = None

            if item_id:
                tags = self.canvas.gettags(item_id)
                if tags and tags[0].startswith(RECT_TAG_PREFIX):
                    clicked_crop_id = tags[0][len(RECT_TAG_PREFIX):]

            if clicked_crop_id:
                # Single click on existing rectangle: Select only this one
                # print(f"Single click selecting: {clicked_crop_id}") # Debug
                self.select_crops([clicked_crop_id], source="single_click")
            else:
                # Single click on empty space: Deselect all
                # print("Single click deselecting all") # Debug
                if self.selected_crop_ids: # Only deselect if something is selected
                    self.select_crops([], source="single_click")

    def on_mouse_drag(self, event):
        if self.is_panning:
            self.on_pan_drag(event)
            return

        # If dragging, it's not a single or double click
        self._double_click_pending = False
        if self._after_id_single_click:
             self.after_cancel(self._after_id_single_click)
             self._after_id_single_click = None

        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.is_resizing:
            # --- Resize Logic (mostly unchanged) ---
            crop_id = self.selected_crop_ids[0] # Should only be one if resizing
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
                 validated_img_coords = self.crops[crop_id]['coords']
                 cx1_f, cy1_f = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                 cx2_f, cy2_f = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                 if cx1_f is not None:
                     try:
                         self.canvas.coords(rect_id, cx1_f, cy1_f, cx2_f, cy2_f)
                     except tk.TclError as e:
                         print(f"Error updating coords during resize: {e}")

        elif self.is_drawing:
            # --- Drawing Logic ---
            if not self.current_rect_id: # Create rect on first drag
                self.current_rect_id = self.canvas.create_rectangle(
                    self.start_x, self.start_y, canvas_x, canvas_y,
                    outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4),
                    tags=("temp_rect",)
                )
                # Ensure drawing deselects previous items
                if self.selected_crop_ids:
                    self.select_crops([], source="draw_start")
            else:
                try:
                    self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)
                except tk.TclError as e:
                    print(f"Error updating coords during draw: {e}")

        elif len(self.selected_crop_ids) == 1: # Check if we *can* move (only single selection)
            # --- Move Logic ---
            # Check if mouse has moved enough to initiate move (prevents accidental tiny moves)
            if not self.is_moving and math.hypot(canvas_x - self.start_x, canvas_y - self.start_y) > 3:
                # Check if the item clicked on press is the currently selected one
                item_id_start = self.find_topmost_crop_rect(self.start_x, self.start_y)
                if item_id_start:
                     tags_start = self.canvas.gettags(item_id_start)
                     start_crop_id = None
                     if tags_start and tags_start[0].startswith(RECT_TAG_PREFIX):
                          start_crop_id = tags_start[0][len(RECT_TAG_PREFIX):]
                     if start_crop_id == self.selected_crop_ids[0]:
                          self.is_moving = True
                          # print("Starting move") # Debug

            if self.is_moving:
                crop_id = self.selected_crop_ids[0]
                if not crop_id in self.crops: return
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
                         cx1_f, cy1_f = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                         cx2_f, cy2_f = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                         if cx1_f is not None:
                             try:
                                 self.canvas.coords(rect_id, cx1_f, cy1_f, cx2_f, cy2_f)
                             except tk.TclError as e:
                                 print(f"Error updating coords during move: {e}")


    def on_mouse_release(self, event):
        """ Handle Button-1 release: Finalize draw/move/resize or schedule single-click action. """
        # If a drag occurred (move/resize/draw), then double_click_pending should be false
        # If no drag, schedule the single-click action check after a short delay
        if not (self.is_moving or self.is_resizing or self.is_drawing):
             # Only schedule if double click is still possible
             if self._double_click_pending:
                 # print("Scheduling single click check") # Debug
                 self._after_id_single_click = self.after(250, lambda e=event: self.handle_single_click_action(e)) # 250ms delay
             # else: Single click was already cancelled by drag start
                 # print("Not scheduling single click, drag cancelled it") # Debug

        # Finalize drawing
        if self.is_drawing and self.current_rect_id:
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            try:
                if self.current_rect_id in self.canvas.find_all():
                    self.canvas.delete(self.current_rect_id)
            except tk.TclError as e:
                print(f"Error deleting temp rect: {e}")


            img_x1, img_y1 = self.canvas_to_image_coords(self.start_x, self.start_y)
            img_x2, img_y2 = self.canvas_to_image_coords(canvas_x, canvas_y)

            if img_x1 is not None and img_x2 is not None:
                 self.add_crop(img_x1, img_y1, img_x2, img_y2)
            else:
                 print("Failed to add crop due to coordinate conversion error.")

        # Reset states AFTER potentially scheduling single click
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.current_rect_id = None
        # Don't reset start_x/y here, needed for potential single click handler
        self.update_cursor(event)


    def on_canvas_double_click(self, event):
        """ Handle Double-Button-1: Immediately select the item, cancel single-click. """
        # print("Double click event received") # Debug
        # Cancel any pending single click action
        if self._after_id_single_click:
            self.after_cancel(self._after_id_single_click)
            self._after_id_single_click = None

        self._double_click_pending = False # Double click happened

        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        item_id = self.find_topmost_crop_rect(canvas_x, canvas_y)

        if item_id:
            tags = self.canvas.gettags(item_id)
            clicked_crop_id = None
            if tags and tags[0].startswith(RECT_TAG_PREFIX):
                 clicked_crop_id = tags[0][len(RECT_TAG_PREFIX):]

            if clicked_crop_id and clicked_crop_id in self.crops:
                # print(f"Double click selecting: {clicked_crop_id}") # Debug
                # Select only this crop on double click
                self.select_crops([clicked_crop_id], source="double_click")
        # else: Double click on empty space - do nothing specific? Deselect?
        # For now, do nothing on empty double click.


    def find_topmost_crop_rect(self, canvas_x, canvas_y):
        try:
            overlapping_ids = self.canvas.find_overlapping(canvas_x - 1, canvas_y - 1, canvas_x + 1, canvas_y + 1)
            for item_id in reversed(overlapping_ids):
                tags = self.canvas.gettags(item_id)
                if "crop_rect" in tags:
                    return item_id
        except tk.TclError as e:
             print(f"Error finding overlapping items: {e}")
        return None

    # --- Zoom and Pan Handlers (Unchanged) ---
    def on_mouse_wheel(self, event, direction=None):
        if not self.original_image: return
        delta = 0
        if direction: delta = direction
        elif hasattr(event, 'delta') and event.delta != 0 : delta = event.delta // abs(event.delta)
        elif event.num == 5: delta = -1
        elif event.num == 4: delta = 1
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
        if not self.original_image or self.is_drawing or self.is_resizing or self.is_moving:
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
        try:
            self.canvas.move("all", dx, dy)
        except tk.TclError as e:
             print(f"Error panning canvas items: {e}") # Catch potential errors if items are bad
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
        selected_ids_from_list = [self.get_crop_id_from_list_index(i) for i in selected_indices]
        selected_ids_from_list = [id for id in selected_ids_from_list if id and id in self.crops]

        # Update internal selection state IF it differs from listbox visual state
        if set(self.selected_crop_ids) != set(selected_ids_from_list):
            # print("Listbox selection changed, calling select_crops") # Debug
            self.select_crops(selected_ids_from_list, source="listbox")
        else:
             # Even if selection is same, button states might need update (e.g., move buttons)
             self.update_button_states()


    def update_listbox_selection_visuals(self):
        """ Ensures the listbox selection visually matches self.selected_crop_ids. """
        # print(f"Updating listbox visuals to match: {self.selected_crop_ids}") # Debug
        # Block the <<ListboxSelect>> event temporarily
        original_binding = self.crop_listbox.bind("<<ListboxSelect>>")
        self.crop_listbox.unbind("<<ListboxSelect>>")

        self.crop_listbox.selection_clear(0, tk.END)
        indices_to_select = []
        for crop_id in self.selected_crop_ids:
            index = self.get_list_index_from_crop_id(crop_id)
            if index != -1:
                indices_to_select.append(index)

        if indices_to_select:
             first_index = indices_to_select[0]
             for index in indices_to_select:
                  self.crop_listbox.selection_set(index)
             self.crop_listbox.activate(first_index) # Make one active
             self.crop_listbox.see(first_index)     # Ensure first selected is visible

        # Re-enable the event binding
        if original_binding: # Restore original binding if it existed
             self.crop_listbox.bind("<<ListboxSelect>>", original_binding)
        else: # If no previous binding, bind to default handler
            self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        # Button states might depend on listbox selection count
        self.update_button_states()


    def on_listbox_double_click(self, event):
        """ Handle double-click in Listbox for renaming. """
        selected_indices = self.crop_listbox.curselection()
        if len(selected_indices) == 1:
            index = selected_indices[0]
            crop_id = self.get_crop_id_from_list_index(index)
            if crop_id and crop_id in self.crops:
                self.prompt_rename_crop(crop_id, index)


    def prompt_rename_crop(self, crop_id, list_index):
        """ Shows a dialog to rename the selected crop. """
        current_name = self.crops[crop_id]['name']
        new_name = simpledialog.askstring("Rename Crop", f"Enter new name for '{current_name}':",
                                          initialvalue=current_name, parent=self)
        if new_name and new_name.strip() and new_name != current_name:
            # Basic check for name conflicts (case-sensitive)
            for other_id, data in self.crops.items():
                 if other_id != crop_id and data['name'] == new_name:
                     messagebox.showwarning("Rename Failed", f"Name '{new_name}' already exists. Please choose a unique name.", parent=self)
                     return

            print(f"Renaming crop {crop_id} from '{current_name}' to '{new_name}'")
            self.crops[crop_id]['name'] = new_name
            # Update the listbox display
            self.rebuild_listbox() # Easiest way to update text & maintain order
            # Reselect the renamed item
            self.crop_listbox.selection_set(list_index)
            self.update_listbox_selection_visuals() # Sync everything


    # --- Listbox Move Button Actions ---
    def move_selected_item_up(self):
        selection = self.crop_listbox.curselection()
        if len(selection) != 1: return # Only move single items

        index = selection[0]
        if index == 0: return # Already at top

        crop_id = self.get_crop_id_from_list_index(index)
        if not crop_id: return

        # Modify order
        self.crop_order.pop(index)
        self.crop_order.insert(index - 1, crop_id)

        # Update UI
        self.rebuild_listbox()
        self.crop_listbox.selection_set(index - 1) # Reselect at new position
        self.update_listbox_selection_visuals() # Sync canvas/buttons

    def move_selected_item_down(self):
        selection = self.crop_listbox.curselection()
        if len(selection) != 1: return

        index = selection[0]
        if index >= self.crop_listbox.size() - 1: return # Already at bottom

        crop_id = self.get_crop_id_from_list_index(index)
        if not crop_id: return

        # Modify order
        self.crop_order.pop(index)
        self.crop_order.insert(index + 1, crop_id)

        # Update UI
        self.rebuild_listbox()
        self.crop_listbox.selection_set(index + 1) # Reselect at new position
        self.update_listbox_selection_visuals() # Sync canvas/buttons


    # --- Resizing Helpers ---
    def get_resize_handle(self, canvas_x, canvas_y, crop_id):
        if not crop_id or crop_id not in self.crops: return None
        rect_id = self.crops[crop_id].get('rect_id')
        if not rect_id or rect_id not in self.canvas.find_all(): return None

        try:
            cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
        except tk.TclError: # Handle cases where coords might fail if item deleted concurrently
             return None

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
        # Determine cursor based on state and position
        new_cursor = ""
        if self.is_panning or self.is_moving:
            new_cursor = "fleur"
        elif self.is_resizing:
            handle = self.resize_handle
            if handle in ('nw', 'se'): new_cursor = "size_nw_se"
            elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
            elif handle in ('n', 's'): new_cursor = "size_ns"
            elif handle in ('e', 'w'): new_cursor = "size_we"
        elif self.is_drawing:
             new_cursor = "crosshair"
        else:
            # Check hover state if not actively doing something else
            if event:
                canvas_x = self.canvas.canvasx(event.x)
                canvas_y = self.canvas.canvasy(event.y)
                handle = None
                hover_move = False

                # Check handles/move only if exactly one item is selected
                if len(self.selected_crop_ids) == 1:
                    selected_id = self.selected_crop_ids[0]
                    handle = self.get_resize_handle(canvas_x, canvas_y, selected_id)
                    if not handle:
                        # Check if hovering inside the selected rectangle
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
                    new_cursor = "fleur"

        # Apply cursor change only if needed
        try:
            if self.canvas.cget("cursor") != new_cursor:
                self.canvas.config(cursor=new_cursor)
        except tk.TclError as e:
            print(f"Error setting cursor: {e}") # Catch potential errors if widget destroyed


    # --- Window Resize Handling ---
    def on_window_resize(self, event=None):
        # Optional: Redraw or refit image. For now, just pass.
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
        output_dir_base = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
        output_dir = os.path.join(output_dir_base, base_name)

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Directory Error", f"Could not create output directory:\n{output_dir}\nError: {e}")
            return

        saved_count = 0
        error_count = 0

        for i, crop_id in enumerate(self.crop_order): # Save uses the current order
            if crop_id not in self.crops:
                print(f"Warning: Skipping crop ID {crop_id} as it's not in the crops dictionary.")
                error_count += 1
                continue

            data = self.crops[crop_id]
            coords = tuple(map(int, data['coords']))
            filename = f"{base_name}_{i + 1}.jpg" # Order determines file number
            filepath = os.path.join(output_dir, filename)

            try:
                cropped_img = self.original_image.crop(coords)
                if cropped_img.mode == 'RGBA':
                    bg = Image.new('RGB', cropped_img.size, (255, 255, 255))
                    bg.paste(cropped_img, (0, 0), cropped_img)
                    cropped_img = bg
                elif cropped_img.mode == 'P':
                     cropped_img = cropped_img.convert('RGB')

                cropped_img.save(filepath, "JPEG", quality=95)
                saved_count += 1
            except Exception as e:
                error_count += 1
                print(f"Error saving {filename} (Crop ID: {crop_id}): {e}")

        if error_count == 0:
            messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to the '{os.path.basename(output_dir)}' folder.")
        else:
            messagebox.showwarning("Partial Success", f"Saved {saved_count} crops to '{os.path.basename(output_dir)}'.\nFailed to save {error_count} crops. Check console for details.")


# --- Run the Application ---
if __name__ == "__main__":
    app = MultiCropApp()
    app.mainloop()
