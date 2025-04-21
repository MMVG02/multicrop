# Required imports
import tkinter as tk
from tkinter import filedialog, messagebox, Listbox
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid
import math
import re # For parsing crop numbers reliably

# --- Constants ---
RECT_TAG_PREFIX = "crop_rect_"
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
# --- Req 4: Clearer Selection Indication ---
SELECTED_RECT_WIDTH = 3 # Make selected rectangle thicker
MIN_CROP_SIZE = 10
# Output folder related constants removed, handled dynamically

# --- Main Application Class ---
class MultiCropApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title("Multi Image Cropper")
        self.geometry("1100x750") # Increased size slightly for status bar etc.
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        # --- State Variables ---
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.tk_image = None
        self.canvas_image_id = None
        # Enhanced crops dictionary: store original order number
        self.crops = {} # {crop_id: {'coords':(x1,y1,x2,y2), 'name': name, 'rect_id': id, 'order': int}}
        self.selected_crop_id = None
        self.next_crop_order_num = 1 # Use this for reliable sorting
        self.last_saved_to_dir = None # --- Req 7: Remember last save directory ---
        self.is_dirty = False # --- Req 8: Track unsaved changes ---

        # Drawing/Editing State (Same as before)
        self.start_x, self.start_y = None, None
        self.current_rect_id = None
        self.is_drawing, self.is_moving, self.is_resizing = False, False, False
        self.resize_handle = None
        self.move_offset_x, self.move_offset_y = 0, 0

        # Zoom/Pan State (Same as before)
        self.zoom_factor = 1.0
        self.pan_start_x, self.pan_start_y = 0, 0
        self.is_panning = False
        self.canvas_offset_x, self.canvas_offset_y = 0, 0

        # --- UI Layout ---
        self.grid_columnconfigure(0, weight=1) # Main area takes all space
        self.grid_rowconfigure(0, weight=1)    # Canvas row takes most space
        self.grid_rowconfigure(1, weight=0)    # Status bar row is fixed height

        # --- Main Content Frame (Canvas + Controls) ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=3) # Image area
        self.main_frame.grid_columnconfigure(1, weight=1) # Control panel
        self.main_frame.grid_rowconfigure(0, weight=1)

        # --- Left Frame (Image Display) ---
        self.image_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.image_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.image_frame.grid_rowconfigure(0, weight=1)
        self.image_frame.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.image_frame, bg="gray90", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # --- Right Frame (Controls) ---
        self.control_frame = ctk.CTkFrame(self.main_frame, width=280) # Slightly wider for new button
        self.control_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False)
        self.control_frame.grid_columnconfigure(0, weight=1)
        self.control_frame.grid_columnconfigure(1, weight=1) # For rename/delete buttons side-by-side
        self.control_frame.grid_rowconfigure(3, weight=1) # Listbox growth

        # Buttons
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image (Ctrl+O)", command=self.handle_open)
        self.btn_select_image.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew")

        self.btn_save_crops = ctk.CTkButton(self.control_frame, text="Save All Crops (Ctrl+S)", command=self.handle_save, state=tk.DISABLED)
        self.btn_save_crops.grid(row=1, column=0, columnspan=2, padx=10, pady=5, sticky="ew")

        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List:")
        self.lbl_crop_list.grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w")

        # Crop Listbox
        self.crop_listbox = Listbox(self.control_frame, bg='white', fg='black',
                                    selectbackground='#CDEAFE', selectforeground='black',
                                    highlightthickness=1, highlightbackground="#CCCCCC",
                                    highlightcolor="#89C4F4", borderwidth=0, exportselection=False)
        self.crop_listbox.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        # --- Req 5: Rename Crops ---
        self.crop_listbox.bind("<Double-Button-1>", self.prompt_rename_selected_crop_event)

        # Rename/Delete Buttons side-by-side
        self.btn_rename_crop = ctk.CTkButton(self.control_frame, text="Rename", command=self.prompt_rename_selected_crop, state=tk.DISABLED)
        self.btn_rename_crop.grid(row=4, column=0, padx=(10, 5), pady=(5, 10), sticky="ew")

        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete (Del)", command=self.delete_selected_crop, state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crop.grid(row=4, column=1, padx=(5, 10), pady=(5, 10), sticky="ew")

        # --- Req 1: Status Bar ---
        self.status_bar = ctk.CTkFrame(self, height=25, fg_color="gray85") # Slightly different color
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=0, pady=(0,0))
        self.status_bar.grid_columnconfigure(0, weight=1) # Left aligned info
        self.status_bar.grid_columnconfigure(1, weight=1) # Center aligned info
        self.status_bar.grid_columnconfigure(2, weight=1) # Right aligned info

        self.lbl_status_coords = ctk.CTkLabel(self.status_bar, text=" Img Coords: --- ", text_color="gray30", height=20, anchor="w")
        self.lbl_status_coords.grid(row=0, column=0, sticky="w", padx=(10, 0))

        self.lbl_status_action = ctk.CTkLabel(self.status_bar, text="Ready", text_color="gray30", height=20, anchor="center")
        self.lbl_status_action.grid(row=0, column=1, sticky="ew")

        self.lbl_status_zoom_select = ctk.CTkLabel(self.status_bar, text="Zoom: 100.0% | Sel: --- ", text_color="gray30", height=20, anchor="e")
        self.lbl_status_zoom_select.grid(row=0, column=2, sticky="e", padx=(0, 10))
        # --- End Status Bar ---

        # --- Bindings ---
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1))
        self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1))
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press)
        self.canvas.bind("<B2-Motion>", self.on_pan_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.on_mouse_motion_canvas) # For status bar coords
        self.canvas.bind("<Enter>", self.on_mouse_motion_canvas) # Update coords when entering canvas
        self.canvas.bind("<Leave>", self.clear_status_coords) # Clear coords when leaving

        # --- Req 3: Keyboard Shortcuts ---
        self.bind("<Control-o>", self.handle_open_event)
        self.bind("<Control-O>", self.handle_open_event) # Handle uppercase O too
        self.bind("<Control-s>", self.handle_save_event)
        self.bind("<Control-S>", self.handle_save_event)
        self.bind("<Delete>", self.delete_selected_crop_event)
        # Nudge shortcuts
        self.bind("<Left>", lambda e: self.handle_nudge(-1, 0))
        self.bind("<Right>", lambda e: self.handle_nudge(1, 0))
        self.bind("<Up>", lambda e: self.handle_nudge(0, -1))
        self.bind("<Down>", lambda e: self.handle_nudge(0, 1))
        # Resize shortcuts (using Shift + Arrows)
        self.bind("<Shift-Left>", lambda e: self.handle_resize_key(-1, 0, 'w')) # Resize left edge
        self.bind("<Shift-Right>", lambda e: self.handle_resize_key(1, 0, 'e')) # Resize right edge
        self.bind("<Shift-Up>", lambda e: self.handle_resize_key(0, -1, 'n'))   # Resize top edge
        self.bind("<Shift-Down>", lambda e: self.handle_resize_key(0, 1, 's')) # Resize bottom edge
        # More resize options (corners - could use Ctrl+Shift)
        # self.bind("<Control-Shift-Left>", lambda e: self.handle_resize_key(-1, -1, 'nw')) # Example

        self.bind("<Configure>", self.on_window_resize)

        # --- Req 8: Unsaved Changes Warning ---
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Initial status bar update
        self.update_status_bar()

    # --- Unsaved Changes Handling (Req 8) ---
    def set_dirty(self, dirty_state=True):
        """Marks the state as having unsaved changes."""
        if self.is_dirty != dirty_state:
            self.is_dirty = dirty_state
            # Optionally, add an asterisk to the window title
            title = "Multi Image Cropper"
            if self.is_dirty:
                title += " *"
            self.title(title)

    def check_unsaved_changes(self):
        """Checks for unsaved changes and prompts user. Returns True if okay to proceed, False otherwise."""
        if not self.is_dirty:
            return True # No unsaved changes

        response = messagebox.askyesnocancel("Unsaved Changes",
                                             "You have unsaved crops. Do you want to save them before proceeding?",
                                             icon=messagebox.WARNING)
        if response is True: # Yes
            self.handle_save() # Attempt to save
            return not self.is_dirty # Proceed only if save was successful (or cancelled but user still wants to proceed - check logic) - let's assume save sets is_dirty=False
        elif response is False: # No
            return True # User chose not to save, okay to proceed
        else: # Cancel
            return False # User cancelled the action, do not proceed

    def on_closing(self):
        """Called when the window close button is pressed."""
        if self.check_unsaved_changes():
            self.destroy() # Close the application

    # --- Status Bar Update (Req 1) ---
    def update_status_bar(self, action_text="Ready", coords_text=" Img Coords: --- ", selection_text=" Sel: --- "):
        """Updates all parts of the status bar."""
        zoom_text = f"Zoom: {self.zoom_factor:.1%}"
        self.lbl_status_coords.configure(text=coords_text)
        self.lbl_status_action.configure(text=action_text)
        self.lbl_status_zoom_select.configure(text=f"{zoom_text} | {selection_text}")

    def clear_status_coords(self, event=None):
        """Clears the coordinate display when mouse leaves canvas."""
        self.update_status_bar(action_text=self.lbl_status_action.cget("text"), # Keep current action text
                               selection_text=self.lbl_status_zoom_select.cget("text").split('|')[1].strip()) # Keep current selection text

    def on_mouse_motion_canvas(self, event):
        """Update coordinates in status bar when mouse moves over canvas."""
        if self.original_image:
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            img_x, img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            coords_text = " Img Coords: --- "
            if img_x is not None and img_y is not None:
                 coords_text = f" Img Coords: {int(img_x):>4}, {int(img_y):>4}"
            self.update_status_bar(action_text=self.lbl_status_action.cget("text"), # Keep current action
                                   coords_text=coords_text,
                                   selection_text=self.lbl_status_zoom_select.cget("text").split('|')[1].strip()) # Keep current selection
        # Also call the cursor update logic
        self.update_cursor(event)

    # --- Shortcut Handlers (Req 3) ---
    def handle_open_event(self, event=None):
        self.handle_open()

    def handle_open(self):
        self.select_image() # select_image now handles the unsaved changes check

    def handle_save_event(self, event=None):
        self.handle_save()

    def handle_save(self):
        if self.crops and self.original_image: # Only proceed if there's something to save
            self.save_crops() # save_crops now handles folder selection and sets dirty=False on success

    def handle_nudge(self, dx_img, dy_img):
        """Nudges the selected crop by dx/dy in image coordinates."""
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            crop_id = self.selected_crop_id
            x1, y1, x2, y2 = self.crops[crop_id]['coords']

            new_x1 = x1 + dx_img
            new_y1 = y1 + dy_img
            new_x2 = x2 + dx_img
            new_y2 = y2 + dy_img

            # Use update_crop_coords which includes validation and bounds checking
            updated = self.update_crop_coords(crop_id, (new_x1, new_y1, new_x2, new_y2))
            if updated:
                self.redraw_all_crops() # Redraw to show the nudge
                self.set_dirty() # Mark as unsaved
                self.update_status_bar_selection() # Update selection info in status bar

    def handle_resize_key(self, dx_img, dy_img, handle):
        """Resizes the selected crop from a specific edge/handle."""
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            crop_id = self.selected_crop_id
            x1, y1, x2, y2 = self.crops[crop_id]['coords']

            nx1, ny1, nx2, ny2 = x1, y1, x2, y2

            # Apply delta based on the handle
            if 'n' in handle: ny1 += dy_img
            if 's' in handle: ny2 += dy_img
            if 'w' in handle: nx1 += dx_img
            if 'e' in handle: nx2 += dx_img

            # Use update_crop_coords for validation (min size, bounds, order)
            updated = self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2))
            if updated:
                self.redraw_all_crops()
                self.set_dirty()
                self.update_status_bar_selection()

    # --- Image Handling (with unsaved changes check) ---
    def select_image(self):
        # --- Req 8: Check before loading new image ---
        if not self.check_unsaved_changes():
            return # User cancelled

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
            if canvas_width <= 1: canvas_width = self.canvas.winfo_reqwidth() # Fallback
            if canvas_height <= 1: canvas_height = self.canvas.winfo_reqheight()

            img_width, img_height = self.original_image.size
            if img_width == 0 or img_height == 0: raise ValueError("Image has zero dimension")

            zoom_h = canvas_width / img_width
            zoom_v = canvas_height / img_height
            initial_zoom = min(zoom_h, zoom_v, 1.0) # Don't zoom > 100% initially
            padding_factor = 0.98
            self.zoom_factor = initial_zoom * padding_factor

            display_w = img_width * self.zoom_factor
            display_h = img_height * self.zoom_factor
            self.canvas_offset_x = math.ceil((canvas_width - display_w) / 2)
            self.canvas_offset_y = math.ceil((canvas_height - display_h) / 2)

            self.clear_crops_and_list()
            self.next_crop_order_num = 1 # Reset crop numbering for new image
            self.last_saved_to_dir = None # Forget last save dir for new image

            self.display_image_on_canvas()
            self.btn_save_crops.configure(state=tk.DISABLED)
            self.set_dirty(False) # Freshly loaded image is not dirty
            self.update_status_bar(action_text="Image Loaded") # Update status

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open or process image:\n{e}")
            self.image_path = None
            self.original_image = None
            self.clear_crops_and_list()
            self.canvas.delete("all")
            self.tk_image = None
            self.display_image = None
            self.btn_save_crops.configure(state=tk.DISABLED)
            self.set_dirty(False)
            self.update_status_bar(action_text="Error Loading Image")

    # --- Crop Handling (with dirty flag and status updates) ---
    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        if not self.original_image: return

        # Validation... (same as before)
        img_w, img_h = self.original_image.size
        x1_img = max(0, min(x1_img, img_w))
        y1_img = max(0, min(y1_img, img_h))
        x2_img = max(0, min(x2_img, img_w))
        y2_img = max(0, min(y2_img, img_h))
        if abs(x2_img - x1_img) < MIN_CROP_SIZE or abs(y2_img - y1_img) < MIN_CROP_SIZE:
            print("Crop too small, ignoring.")
            if self.current_rect_id: self.canvas.delete(self.current_rect_id)
            self.current_rect_id = None
            self.update_status_bar(action_text="Crop Too Small") # Update status
            return

        coords = (min(x1_img, x2_img), min(y1_img, y2_img),
                  max(x1_img, x2_img), max(y1_img, y2_img))

        crop_id = str(uuid.uuid4())
        # Use a simple default name initially, rely on rename function
        crop_name = f"Crop_{self.next_crop_order_num}"
        current_order_num = self.next_crop_order_num
        self.next_crop_order_num += 1

        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])
        if cx1 is None: return

        # Use appropriate width based on selection state (it will be selected initially)
        rect_id = self.canvas.create_rectangle(
            cx1, cy1, cx2, cy2,
            outline=SELECTED_RECT_COLOR, width=SELECTED_RECT_WIDTH, # Create as selected
            tags=(RECT_TAG_PREFIX + crop_id, "crop_rect")
        )

        self.crops[crop_id] = {
            'coords': coords,
            'name': crop_name,
            'rect_id': rect_id,
            'order': current_order_num # Store original order
        }

        # Add to listbox and select it
        self.crop_listbox.insert(tk.END, crop_name)
        self.crop_listbox.selection_clear(0, tk.END)
        self.crop_listbox.selection_set(tk.END)
        # Manually trigger selection logic for the new item
        self.select_crop(crop_id, from_listbox=False) # Pass the new crop_id

        self.btn_save_crops.configure(state=tk.NORMAL)
        self.btn_delete_crop.configure(state=tk.NORMAL)
        self.btn_rename_crop.configure(state=tk.NORMAL)
        self.set_dirty() # Mark changes as unsaved
        self.update_status_bar(action_text="Crop Added") # Update status

    def select_crop(self, crop_id, from_listbox=True):
        if self.selected_crop_id == crop_id and crop_id is not None:
            self.update_status_bar_selection() # Update selection info even if already selected
            return

        # Deselect previous
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            prev_data = self.crops[self.selected_crop_id]
            if prev_data['rect_id'] in self.canvas.find_withtag(prev_data['rect_id']):
                 # --- Req 4: Use normal width when deselecting ---
                 self.canvas.itemconfig(prev_data['rect_id'], outline=DEFAULT_RECT_COLOR, width=RECT_WIDTH)

        self.selected_crop_id = crop_id

        # Select new
        if crop_id and crop_id in self.crops:
            data = self.crops[crop_id]
            if data['rect_id'] in self.canvas.find_withtag(data['rect_id']):
                 # --- Req 4: Use selected width when selecting ---
                 self.canvas.itemconfig(data['rect_id'], outline=SELECTED_RECT_COLOR, width=SELECTED_RECT_WIDTH)
                 self.canvas.tag_raise(data['rect_id'])
                 self.btn_delete_crop.configure(state=tk.NORMAL)
                 self.btn_rename_crop.configure(state=tk.NORMAL) # Enable rename button

                 if not from_listbox:
                     # Find and select in listbox
                     index = -1
                     for i in range(self.crop_listbox.size()):
                         if self.crop_listbox.get(i) == data['name']:
                             index = i
                             break
                     if index != -1:
                         self.crop_listbox.selection_clear(0, tk.END)
                         self.crop_listbox.selection_set(index)
                         self.crop_listbox.activate(index)
                         self.crop_listbox.see(index)
            else:
                 # Stale rect ID
                 print(f"Warning: Stale rectangle ID {data['rect_id']} for crop {crop_id}")
                 self.selected_crop_id = None
                 self.btn_delete_crop.configure(state=tk.DISABLED)
                 self.btn_rename_crop.configure(state=tk.DISABLED) # Disable rename button
        else:
            # No valid crop selected or crop_id is None
            self.selected_crop_id = None
            if not from_listbox:
                self.crop_listbox.selection_clear(0, tk.END)
            self.btn_delete_crop.configure(state=tk.DISABLED)
            self.btn_rename_crop.configure(state=tk.DISABLED) # Disable rename button

        self.update_status_bar_selection() # Update status bar selection info

    def update_status_bar_selection(self):
        """Updates the selection part of the status bar."""
        selection_text = " Sel: --- "
        if self.selected_crop_id and self.selected_crop_id in self.crops:
             coords = self.crops[self.selected_crop_id]['coords']
             w = int(coords[2] - coords[0])
             h = int(coords[3] - coords[1])
             selection_text = f" Sel: {w}x{h} px"
        # Keep existing coord/action text when updating selection
        self.update_status_bar(action_text=self.lbl_status_action.cget("text"),
                               coords_text=self.lbl_status_coords.cget("text"),
                               selection_text=selection_text)

    def redraw_all_crops(self):
        all_canvas_items = self.canvas.find_all()
        for crop_id, data in self.crops.items():
            img_x1, img_y1, img_x2, img_y2 = data['coords']
            cx1, cy1 = self.image_to_canvas_coords(img_x1, img_y1)
            cx2, cy2 = self.image_to_canvas_coords(img_x2, img_y2)
            if cx1 is None: continue

            # --- Req 4: Use appropriate width ---
            is_selected = (crop_id == self.selected_crop_id)
            color = SELECTED_RECT_COLOR if is_selected else DEFAULT_RECT_COLOR
            width = SELECTED_RECT_WIDTH if is_selected else RECT_WIDTH
            tags_tuple = (RECT_TAG_PREFIX + crop_id, "crop_rect")

            if data['rect_id'] in all_canvas_items:
                 self.canvas.coords(data['rect_id'], cx1, cy1, cx2, cy2)
                 self.canvas.itemconfig(data['rect_id'], outline=color, width=width, tags=tags_tuple)
            else:
                 rect_id = self.canvas.create_rectangle(
                     cx1, cy1, cx2, cy2, outline=color, width=width, tags=tags_tuple)
                 self.crops[crop_id]['rect_id'] = rect_id

        # Ensure selected is on top
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            selected_rect_id = self.crops[self.selected_crop_id]['rect_id']
            if selected_rect_id in self.canvas.find_all():
                 self.canvas.tag_raise(selected_rect_id)

        self.update_status_bar_selection() # Update selection info after redraw

    def delete_selected_crop_event(self, event=None):
        self.delete_selected_crop()

    def delete_selected_crop(self):
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            return

        crop_id_to_delete = self.selected_crop_id
        data = self.crops[crop_id_to_delete]

        # Remove from canvas
        if data['rect_id'] in self.canvas.find_all():
             self.canvas.delete(data['rect_id'])

        # Find listbox index before deleting data
        index_to_delete = -1
        current_name = data['name']
        for i in range(self.crop_listbox.size()):
            if self.crop_listbox.get(i) == current_name:
                index_to_delete = i
                break

        # Remove from internal dictionary
        del self.crops[crop_id_to_delete]

        # Remove from listbox
        if index_to_delete != -1:
            self.crop_listbox.delete(index_to_delete)

        # Reset selection state
        self.selected_crop_id = None
        self.btn_delete_crop.configure(state=tk.DISABLED)
        self.btn_rename_crop.configure(state=tk.DISABLED)
        if not self.crops:
             self.btn_save_crops.configure(state=tk.DISABLED)

        self.set_dirty() # Mark changes as unsaved
        self.update_status_bar(action_text="Crop Deleted") # Update status

        # Select the next item in the list if possible
        if self.crop_listbox.size() > 0:
            new_index = max(0, index_to_delete - 1) if index_to_delete != -1 else 0
            if index_to_delete != -1 and new_index >= self.crop_listbox.size(): # Adjust if last item deleted
                new_index = self.crop_listbox.size() - 1
            self.crop_listbox.selection_set(new_index)
            self.on_listbox_select() # Trigger selection logic
        else:
            self.crop_listbox.selection_clear(0, tk.END)
            self.select_crop(None, from_listbox=False) # Explicitly deselect

    # --- Rename Crop (Req 5) ---
    def prompt_rename_selected_crop_event(self, event=None):
        self.prompt_rename_selected_crop()

    def prompt_rename_selected_crop(self):
        """Shows a dialog to rename the selected crop."""
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            messagebox.showwarning("Rename Error", "Please select a crop to rename.")
            return

        crop_id = self.selected_crop_id
        current_name = self.crops[crop_id]['name']

        dialog = ctk.CTkInputDialog(text="Enter new name for the crop:", title="Rename Crop",
                                    entry_fg_color="white", entry_text_color="black") # Light theme entry
        new_name_raw = dialog.get_input()

        if new_name_raw is None or new_name_raw.strip() == "":
            return # User cancelled or entered empty name

        new_name = new_name_raw.strip()

        # Check for duplicate names (optional but good practice)
        for c_id, data in self.crops.items():
            if c_id != crop_id and data['name'] == new_name:
                messagebox.showerror("Rename Error", f"A crop named '{new_name}' already exists.")
                return

        # Update internal data
        self.crops[crop_id]['name'] = new_name

        # Update listbox display
        index = -1
        for i in range(self.crop_listbox.size()):
            if self.crop_listbox.get(i) == current_name: # Find by old name
                index = i
                break
        if index != -1:
            self.crop_listbox.delete(index)
            self.crop_listbox.insert(index, new_name) # Insert new name at same position
            self.crop_listbox.selection_set(index) # Re-select the item
            self.crop_listbox.activate(index)

        self.set_dirty() # Mark unsaved changes
        self.update_status_bar(action_text="Crop Renamed")

    # --- Mouse Events (with status updates) ---
    def on_mouse_press(self, event):
        self.canvas.focus_set()
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        action_text = "Ready" # Default

        handle = self.get_resize_handle(canvas_x, canvas_y)
        if handle and self.selected_crop_id:
            self.is_resizing = True
            self.resize_handle = handle
            self.start_x, self.start_y = canvas_x, canvas_y
            self.start_coords_img = self.crops[self.selected_crop_id]['coords']
            action_text = "Resizing Crop..."
        else:
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
                self.select_crop(clicked_crop_id) # select_crop updates status selection part
                self.is_moving = True
                rect_coords = self.canvas.coords(self.crops[clicked_crop_id]['rect_id'])
                self.move_offset_x = canvas_x - rect_coords[0]
                self.move_offset_y = canvas_y - rect_coords[1]
                action_text = "Moving Crop..."
            elif self.original_image:
                 self.is_drawing = True
                 self.start_x, self.start_y = canvas_x, canvas_y
                 self.current_rect_id = self.canvas.create_rectangle(
                     self.start_x, self.start_y, self.start_x, self.start_y,
                     outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4), tags=("temp_rect",))
                 self.select_crop(None) # Deselect any existing
                 action_text = "Drawing Crop..."

        self.update_status_bar(action_text=action_text) # Update status action

    def on_mouse_drag(self, event):
        # No status change needed during drag itself usually, action set on press
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.is_drawing and self.current_rect_id:
            self.canvas.coords(self.current_rect_id, self.start_x, self.start_y, canvas_x, canvas_y)
        elif self.is_moving and self.selected_crop_id:
            # ... (move logic as before) ...
            # Update stored coordinates (includes validation)
            # ...
            if self.update_crop_coords(self.selected_crop_id, (img_x1, img_y1, img_x2, img_y2)):
                 self.redraw_all_crops() # Use redraw to ensure correct width/position
                 self.set_dirty()
                 self.update_status_bar_selection() # Update size display while moving
        elif self.is_resizing and self.selected_crop_id and self.resize_handle:
            # ... (resize logic as before) ...
            # Update stored coords (includes validation)
            # ...
            if self.update_crop_coords(self.selected_crop_id, (nx1, ny1, nx2, ny2)):
                self.redraw_all_crops() # Use redraw to ensure correct width/position
                self.set_dirty()
                self.update_status_bar_selection() # Update size display while resizing

    def on_mouse_release(self, event):
        if self.is_drawing and self.current_rect_id:
            # ... (add_crop logic as before) ...
            if self.current_rect_id in self.canvas.find_withtag("temp_rect"):
                self.canvas.delete(self.current_rect_id)
            # ... (convert coords and call self.add_crop) ...
        # Reset states
        self.is_drawing, self.is_moving, self.is_resizing = False, False, False
        self.resize_handle, self.current_rect_id = None, None
        self.update_cursor(event)
        self.update_status_bar(action_text="Ready") # Reset status action

    # --- Zoom/Pan (with status updates) ---
    def on_mouse_wheel(self, event, direction=None):
        # ... (zoom logic as before) ...
        if new_zoom != self.zoom_factor:
            # ... (update zoom factor and offset) ...
            self.display_image_on_canvas()
            self.update_status_bar() # Update zoom display

    def on_pan_press(self, event):
        if not self.original_image: return
        self.is_panning = True
        self.pan_start_x = self.canvas.canvasx(event.x)
        self.pan_start_y = self.canvas.canvasy(event.y)
        self.canvas.config(cursor="fleur")
        self.update_status_bar(action_text="Panning...") # Update status action

    def on_pan_release(self, event):
        self.is_panning = False
        self.update_cursor(event)
        self.update_status_bar(action_text="Ready") # Reset status action

    # --- Listbox Selection (updates status) ---
    def on_listbox_select(self, event=None):
        selection = self.crop_listbox.curselection()
        selected_id = None
        if selection:
            selected_index = selection[0]
            selected_name = self.crop_listbox.get(selected_index)
            for crop_id, data in self.crops.items():
                if data['name'] == selected_name:
                    selected_id = crop_id
                    break
        # select_crop handles the actual selection logic and status update
        self.select_crop(selected_id, from_listbox=True)

    # --- Saving Crops (with folder selection) ---
    def save_crops(self):
        if not self.original_image or not self.image_path:
            messagebox.showwarning("No Image", "Please select an image first.")
            return
        if not self.crops:
            messagebox.showwarning("No Crops", "Please define at least one crop area.")
            return

        # --- Req 7: Choose Output Folder ---
        initial_dir = self.last_saved_to_dir # Start in last used dir
        # Default suggestion: folder named after image in image's original directory
        if not initial_dir:
            img_dir = os.path.dirname(self.image_path)
            base_name = os.path.splitext(os.path.basename(self.image_path))[0]
            initial_dir = os.path.join(img_dir, base_name)

        output_dir = filedialog.askdirectory(
            title="Select Folder to Save Crops",
            initialdir=initial_dir # Suggest last used or image-based folder
        )

        if not output_dir: # User cancelled
            self.update_status_bar(action_text="Save Cancelled")
            return

        self.last_saved_to_dir = output_dir # Remember for next time

        # Ensure the chosen directory exists (it should, askdirectory verifies)
        # os.makedirs(output_dir, exist_ok=True) # Usually not needed after askdirectory

        saved_count = 0
        error_count = 0

        # Sort crops by their original creation order for sequential saving
        def get_crop_order(item_tuple):
            crop_id, data = item_tuple
            return data.get('order', float('inf')) # Use stored order number

        sorted_crop_items = sorted(self.crops.items(), key=get_crop_order)

        self.update_status_bar(action_text="Saving...")
        self.update_idletasks() # Show status update immediately

        for i, (crop_id, data) in enumerate(sorted_crop_items, start=1):
            coords = tuple(map(int, data['coords']))
            # Use the current (potentially renamed) crop name for the file
            # Sanitize the name slightly for filesystem compatibility
            safe_crop_name = re.sub(r'[\\/*?:"<>|]', '_', data['name']) # Replace invalid chars
            filename = f"{safe_crop_name}.jpg" # Save using current name
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

        # --- Req 8: Clear dirty flag after successful save ---
        if error_count == 0:
            self.set_dirty(False)
            messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to:\n{output_dir}")
            self.update_status_bar(action_text="Crops Saved")
        else:
            # Decide if partially successful save should clear dirty flag? Maybe not.
            messagebox.showwarning("Partial Success", f"Saved {saved_count} crops to:\n{output_dir}\nFailed to save {error_count} crops. Check console/log.")
            self.update_status_bar(action_text="Save Complete (with errors)")


    # --- Helper Functions (like coordinate conversions, redraw, etc.) ---
    # (Keep existing helper functions: display_image_on_canvas, clear_crops_and_list,
    # canvas_to_image_coords, image_to_canvas_coords, update_crop_coords,
    # get_resize_handle, update_cursor, on_window_resize)
    # Make sure update_crop_coords sets the dirty flag:
    def update_crop_coords(self, crop_id, new_img_coords):
        if crop_id in self.crops and self.original_image:
             img_w, img_h = self.original_image.size
             x1, y1, x2, y2 = new_img_coords
             # Clamp, validate order, check min size... (same logic as before)
             # ...
             if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE:
                 return False

             # Only set dirty if coords actually change
             if self.crops[crop_id]['coords'] != (final_x1, final_y1, final_x2, final_y2):
                  self.crops[crop_id]['coords'] = (final_x1, final_y1, final_x2, final_y2)
                  self.set_dirty() # Set dirty flag here on successful change
                  return True
             else:
                  return True # Return true even if no change, coords are valid

        return False

    def clear_crops_and_list(self):
        """Clears existing crops, listbox, and resets related states."""
        self.canvas.delete("crop_rect") # Delete only crop rectangles
        self.crops.clear()
        self.crop_listbox.delete(0, tk.END)
        self.selected_crop_id = None
        self.btn_delete_crop.configure(state=tk.DISABLED)
        # Keep next_crop_number until a new image is loaded or manually reset if needed

    def display_image_on_canvas(self):
        """Displays the current self.display_image on the canvas respecting zoom and pan."""
        if not self.original_image:
            self.canvas.delete("all") # Clear if no image
            return

        disp_w = int(self.original_image.width * self.zoom_factor)
        disp_h = int(self.original_image.height * self.zoom_factor)

        # Ensure minimum display size to avoid errors with tiny zooms
        disp_w = max(1, disp_w)
        disp_h = max(1, disp_h)

        try:
            # Use LANCZOS for better quality resizing
            self.display_image = self.original_image.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        except Exception as e:
             print(f"Error resizing image: {e}")
             # Fallback or handle differently? For now, try to continue.
             self.display_image = None # Indicate failure
             self.canvas.delete("all")
             return


        self.tk_image = ImageTk.PhotoImage(self.display_image)

        # Clear previous image and rectangles before drawing new ones
        self.canvas.delete("all") # Clear everything first

        # Draw image at current pan offset
        # Ensure offsets are integers for create_image
        int_offset_x = int(round(self.canvas_offset_x))
        int_offset_y = int(round(self.canvas_offset_y))

        self.canvas_image_id = self.canvas.create_image(
            int_offset_x, int_offset_y,
            anchor=tk.NW, image=self.tk_image, tags="image"
        )

        # Redraw all crop rectangles based on new zoom/pan
        self.redraw_all_crops()


    # --- Coordinate Conversion ---
    def canvas_to_image_coords(self, canvas_x, canvas_y):
        """Convert canvas coordinates to original image coordinates."""
        if not self.original_image or self.zoom_factor == 0: return None, None # Avoid division by zero
        img_x = (canvas_x - self.canvas_offset_x) / self.zoom_factor
        img_y = (canvas_y - self.canvas_offset_y) / self.zoom_factor
        return img_x, img_y

    def image_to_canvas_coords(self, img_x, img_y):
        """Convert original image coordinates to canvas coordinates."""
        if not self.original_image: return None, None
        canvas_x = (img_x * self.zoom_factor) + self.canvas_offset_x
        canvas_y = (img_y * self.zoom_factor) + self.canvas_offset_y
        return canvas_x, canvas_y

    # --- Crop Handling ---
    def add_crop(self, x1_img, y1_img, x2_img, y2_img):
        """Adds a new crop definition and draws it."""
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
        # Use the base name for the generic crop name part
        base_name = "Image" # Default if no path yet
        if self.image_path:
             base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        crop_name = f"{base_name}_Crop_{self.next_crop_number}" # More descriptive default name
        self.next_crop_number += 1

        cx1, cy1 = self.image_to_canvas_coords(coords[0], coords[1])
        cx2, cy2 = self.image_to_canvas_coords(coords[2], coords[3])

        # Check if conversion failed (e.g., image not loaded)
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

        self.crop_listbox.insert(tk.END, crop_name)
        self.crop_listbox.selection_clear(0, tk.END)
        self.crop_listbox.selection_set(tk.END)
        # Manually trigger selection logic after insert
        self.select_crop(crop_id, from_listbox=False) # Pass the new crop_id

        self.btn_save_crops.configure(state=tk.NORMAL)
        self.btn_delete_crop.configure(state=tk.NORMAL)

    def select_crop(self, crop_id, from_listbox=True):
        """Selects a crop by its ID, updates visuals."""
        if self.selected_crop_id == crop_id and crop_id is not None:
            return # Already selected

        # Deselect previous
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            prev_rect_id = self.crops[self.selected_crop_id]['rect_id']
            # Check if the rectangle still exists on canvas before trying to configure it
            if prev_rect_id in self.canvas.find_withtag(prev_rect_id):
                 self.canvas.itemconfig(prev_rect_id, outline=DEFAULT_RECT_COLOR)

        self.selected_crop_id = crop_id

        # Select new
        if crop_id and crop_id in self.crops:
            rect_id = self.crops[crop_id]['rect_id']
            # Check if the rectangle still exists on canvas
            if rect_id in self.canvas.find_withtag(rect_id):
                 self.canvas.itemconfig(rect_id, outline=SELECTED_RECT_COLOR)
                 self.canvas.tag_raise(rect_id) # Bring selected rectangle to front
                 self.btn_delete_crop.configure(state=tk.NORMAL)

                 # Update listbox selection if not triggered by it
                 if not from_listbox:
                     index = -1
                     for i in range(self.crop_listbox.size()):
                         # Find listbox item by matching the name associated with the crop_id
                         if self.crop_listbox.get(i) == self.crops[crop_id]['name']:
                             index = i
                             break
                     if index != -1:
                         self.crop_listbox.selection_clear(0, tk.END)
                         self.crop_listbox.selection_set(index)
                         self.crop_listbox.activate(index)
                         self.crop_listbox.see(index) # Ensure visible
            else:
                 # Rectangle ID is invalid (e.g., after image reload/clear)
                 print(f"Warning: Stale rectangle ID {rect_id} for crop {crop_id}")
                 self.selected_crop_id = None # Mark as deselected
                 self.btn_delete_crop.configure(state=tk.DISABLED)

        else:
            # No valid crop selected or crop_id is None
            self.selected_crop_id = None
            if not from_listbox: # If deselection wasn't from listbox click, clear listbox selection
                self.crop_listbox.selection_clear(0, tk.END)
            self.btn_delete_crop.configure(state=tk.DISABLED)


    def update_crop_coords(self, crop_id, new_img_coords):
        """Updates the stored original image coordinates for a crop."""
        if crop_id in self.crops and self.original_image:
             img_w, img_h = self.original_image.size
             x1, y1, x2, y2 = new_img_coords
             # Clamp coordinates to image bounds
             x1 = max(0, min(x1, img_w))
             y1 = max(0, min(y1, img_h))
             x2 = max(0, min(x2, img_w))
             y2 = max(0, min(y2, img_h))
             # Ensure x1 < x2, y1 < y2 and minimum size
             final_x1 = min(x1, x2)
             final_y1 = min(y1, y2)
             final_x2 = max(x1, x2)
             final_y2 = max(y1, y2)
             # Re-check min size after potential clamping/swapping
             if (final_x2 - final_x1) < MIN_CROP_SIZE or (final_y2 - final_y1) < MIN_CROP_SIZE:
                 # Don't update if it violates min size constraints during move/resize
                 # This prevents rect from collapsing or becoming invalid
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

            # Handle case where conversion might fail (e.g., zoom is zero)
            if cx1 is None: continue

            color = SELECTED_RECT_COLOR if crop_id == self.selected_crop_id else DEFAULT_RECT_COLOR
            tags_tuple = (RECT_TAG_PREFIX + crop_id, "crop_rect") # Ensure tags are tuple

            if data['rect_id'] in all_canvas_items:
                 # If rectangle exists, update its coordinates and color
                 self.canvas.coords(data['rect_id'], cx1, cy1, cx2, cy2)
                 self.canvas.itemconfig(data['rect_id'], outline=color, tags=tags_tuple)
            else:
                 # If rectangle doesn't exist (e.g., after image reload), recreate it
                 # print(f"Debug: Recreating rectangle for crop {crop_id}")
                 rect_id = self.canvas.create_rectangle(
                     cx1, cy1, cx2, cy2,
                     outline=color, width=RECT_WIDTH,
                     tags=tags_tuple
                 )
                 # Update the stored rect_id for this crop
                 self.crops[crop_id]['rect_id'] = rect_id

        # Ensure selected is on top after all are drawn/updated
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            selected_rect_id = self.crops[self.selected_crop_id]['rect_id']
            if selected_rect_id in self.canvas.find_all(): # Check if exists before raising
                 self.canvas.tag_raise(selected_rect_id)


    def delete_selected_crop_event(self, event=None):
        """Handles delete key press."""
        self.delete_selected_crop()

    def delete_selected_crop(self):
        """Deletes the currently selected crop."""
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            return

        crop_id_to_delete = self.selected_crop_id
        data = self.crops[crop_id_to_delete]

        # Remove from canvas - check if it exists first
        if data['rect_id'] in self.canvas.find_all():
             self.canvas.delete(data['rect_id'])

        # Find index before deleting from listbox
        index_to_delete = -1
        for i in range(self.crop_listbox.size()):
            if self.crop_listbox.get(i) == data['name']:
                index_to_delete = i
                break

        # Remove from internal dictionary *first*
        del self.crops[crop_id_to_delete]

        # Remove from listbox if found
        if index_to_delete != -1:
            self.crop_listbox.delete(index_to_delete)

        # Reset selection state *after* listbox manipulation
        self.selected_crop_id = None
        self.btn_delete_crop.configure(state=tk.DISABLED)
        if not self.crops:
             self.btn_save_crops.configure(state=tk.DISABLED)

        # Select the next item in the list if possible
        if self.crop_listbox.size() > 0:
            new_index = max(0, index_to_delete -1) if index_to_delete != -1 else 0 # Select previous or first
            # If deleted last item, select new last item
            if index_to_delete != -1 and new_index >= self.crop_listbox.size():
                 new_index = self.crop_listbox.size() - 1

            self.crop_listbox.selection_set(new_index)
            self.on_listbox_select() # Trigger selection logic for the new selection
        else:
             # No items left, ensure everything is deselected visually
             self.crop_listbox.selection_clear(0, tk.END)
             self.select_crop(None, from_listbox=False) # Explicitly deselect internal state


    # --- Mouse Event Handlers ---
    def on_mouse_press(self, event):
        self.canvas.focus_set() # Set focus to canvas for keyboard events (like Delete)
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        # Check if clicking on a resize handle of the selected crop
        handle = self.get_resize_handle(canvas_x, canvas_y)
        if handle and self.selected_crop_id:
            self.is_resizing = True
            self.resize_handle = handle
            self.start_x = canvas_x
            self.start_y = canvas_y
            # Store the original image coords *before* resizing starts
            self.start_coords_img = self.crops[self.selected_crop_id]['coords']
            return

        # Check if clicking inside an existing rectangle to select/move it
        # Need to find items tagged "crop_rect" near the click
        overlapping_items = self.canvas.find_overlapping(canvas_x-1, canvas_y-1, canvas_x+1, canvas_y+1)
        clicked_crop_id = None
        for item_id in reversed(overlapping_items): # Check topmost first
             tags = self.canvas.gettags(item_id)
             if tags and tags[0].startswith(RECT_TAG_PREFIX) and "crop_rect" in tags:
                  crop_id = tags[0][len(RECT_TAG_PREFIX):]
                  if crop_id in self.crops:
                       clicked_crop_id = crop_id
                       break # Found the topmost crop rect

        if clicked_crop_id:
            self.select_crop(clicked_crop_id)
            self.is_moving = True
            # Record mouse offset relative to the top-left corner of the rect
            rect_coords = self.canvas.coords(self.crops[clicked_crop_id]['rect_id'])
            self.move_offset_x = canvas_x - rect_coords[0]
            self.move_offset_y = canvas_y - rect_coords[1]
            return # Don't start drawing a new rectangle

        # If not clicking on a handle or existing rect, start drawing a new one
        if self.original_image: # Only allow drawing if an image is loaded
             self.is_drawing = True
             self.start_x = canvas_x
             self.start_y = canvas_y
             # Create a temporary dashed rectangle
             self.current_rect_id = self.canvas.create_rectangle(
                 self.start_x, self.start_y, self.start_x, self.start_y,
                 outline=SELECTED_RECT_COLOR, width=RECT_WIDTH, dash=(4, 4),
                 tags=("temp_rect",) # Tag it temporarily
             )
             # Deselect any currently selected crop
             self.select_crop(None)


    def on_mouse_drag(self, event):
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

        if self.is_drawing and self.current_rect_id:
            # Update the temporary drawing rectangle
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

            # Convert new canvas coords back to original image coords for validation/storage
            img_x1, img_y1 = self.canvas_to_image_coords(new_cx1, new_cy1)
            img_x2, img_y2 = self.canvas_to_image_coords(new_cx2, new_cy2)

            if img_x1 is not None: # Check conversion was successful
                # Update stored coordinates (includes bounds check)
                updated = self.update_crop_coords(crop_id, (img_x1, img_y1, img_x2, img_y2))
                if updated:
                     # If coords updated successfully, redraw the rect on canvas
                     # Use the *validated* coords from storage, converted back to canvas
                     validated_img_coords = self.crops[crop_id]['coords']
                     cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                     cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                     self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)

        elif self.is_resizing and self.selected_crop_id and self.resize_handle:
            crop_id = self.selected_crop_id
            rect_id = self.crops[crop_id]['rect_id']

            # Use the stored coords *before* the resize started as the base
            ox1_img, oy1_img, ox2_img, oy2_img = self.start_coords_img

            # Convert current mouse canvas coords to image coords
            curr_img_x, curr_img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
            # Convert starting mouse canvas coords to image coords
            start_img_x, start_img_y = self.canvas_to_image_coords(self.start_x, self.start_y)

            if curr_img_x is None or start_img_x is None: return # Bail if conversion fails

            # Calculate mouse delta in image coordinates
            dx_img = curr_img_x - start_img_x
            dy_img = curr_img_y - start_img_y

            nx1, ny1, nx2, ny2 = ox1_img, oy1_img, ox2_img, oy2_img

            # Apply delta based on the handle being dragged
            if 'n' in self.resize_handle: ny1 += dy_img
            if 's' in self.resize_handle: ny2 += dy_img
            if 'w' in self.resize_handle: nx1 += dx_img
            if 'e' in self.resize_handle: nx2 += dx_img

            # Update stored coords (includes validation like min size, bounds, x1<x2)
            updated = self.update_crop_coords(crop_id, (nx1, ny1, nx2, ny2))

            if updated:
                 # If coords updated successfully, redraw the rect on canvas
                 validated_img_coords = self.crops[crop_id]['coords']
                 cx1_final, cy1_final = self.image_to_canvas_coords(validated_img_coords[0], validated_img_coords[1])
                 cx2_final, cy2_final = self.image_to_canvas_coords(validated_img_coords[2], validated_img_coords[3])
                 self.canvas.coords(rect_id, cx1_final, cy1_final, cx2_final, cy2_final)


    def on_mouse_release(self, event):
        if self.is_drawing and self.current_rect_id:
            # Finalize the new crop
            canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
            # Delete the temporary dashed rect (check existence first)
            if self.current_rect_id in self.canvas.find_withtag("temp_rect"):
                 self.canvas.delete(self.current_rect_id)

            # Convert start and end canvas coords to image coords
            img_x1, img_y1 = self.canvas_to_image_coords(self.start_x, self.start_y)
            img_x2, img_y2 = self.canvas_to_image_coords(canvas_x, canvas_y)

            if img_x1 is not None and img_y1 is not None and img_x2 is not None and img_y2 is not None: # Check conversion success
                 self.add_crop(img_x1, img_y1, img_x2, img_y2)
            else:
                 print("Failed to add crop due to coordinate conversion error.")

        # Reset states
        self.is_drawing = False
        self.is_moving = False
        self.is_resizing = False
        self.resize_handle = None
        self.current_rect_id = None
        # Don't reset start_x/y here, they are set on press
        self.update_cursor(event) # Reset cursor


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
        min_zoom = 0.01 # Allow zooming out further
        max_zoom = 20.0

        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)

        img_x_before, img_y_before = self.canvas_to_image_coords(canvas_x, canvas_y)
        if img_x_before is None: return # Cannot zoom if coords are invalid

        if delta > 0:
            new_zoom = self.zoom_factor * zoom_increment
        else:
            new_zoom = self.zoom_factor / zoom_increment
        new_zoom = max(min_zoom, min(max_zoom, new_zoom))

        if new_zoom == self.zoom_factor: return

        self.zoom_factor = new_zoom

        # Recalculate offset to keep the point under the mouse stationary
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

        # Update canvas offset (image top-left relative to canvas top-left)
        self.canvas_offset_x += dx
        self.canvas_offset_y += dy

        # Move the image *and* all crop rectangles visually on the canvas
        self.canvas.move("all", dx, dy) # More efficient than looping? Check performance if many items

        # Update start position for next drag increment
        self.pan_start_x = current_x
        self.pan_start_y = current_y

    def on_pan_release(self, event):
        self.is_panning = False
        # Reset cursor based on current position (might be over a handle)
        self.update_cursor(event)


    # --- Listbox Selection ---
    def on_listbox_select(self, event=None):
        selection = self.crop_listbox.curselection()
        if not selection:
             # Selection cleared in listbox, deselect internally too
             if self.selected_crop_id:
                 self.select_crop(None, from_listbox=True)
             return

        selected_index = selection[0]
        selected_name = self.crop_listbox.get(selected_index)

        found_id = None
        for crop_id, data in self.crops.items():
            if data['name'] == selected_name:
                found_id = crop_id
                break

        if found_id:
            self.select_crop(found_id, from_listbox=True)
        else:
             # Name in listbox doesn't match any current crop? Should not happen.
             print(f"Warning: Listbox name '{selected_name}' not found in crops.")
             self.select_crop(None, from_listbox=True)


    # --- Resizing Helpers ---
    def get_resize_handle(self, canvas_x, canvas_y):
        """Checks if the cursor is near a resize handle of the selected crop."""
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:
            return None

        rect_id = self.crops[self.selected_crop_id]['rect_id']
        # Check if rect_id is valid before getting coords
        if rect_id not in self.canvas.find_all():
            # print(f"Debug: get_resize_handle called with invalid rect_id {rect_id}")
            return None

        cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
        handle_margin = 6 # Pixels around corners/edges to detect handle

        # Check corners first
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'nw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy1) < handle_margin: return 'ne'
        if abs(canvas_x - cx1) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'sw'
        if abs(canvas_x - cx2) < handle_margin and abs(canvas_y - cy2) < handle_margin: return 'se'

        # Check edges if not on corner
        # Add a small inner buffer to avoid edge detection when inside
        inner_buffer = handle_margin / 2
        if abs(canvas_y - cy1) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 'n'
        if abs(canvas_y - cy2) < handle_margin and (cx1 + inner_buffer) < canvas_x < (cx2 - inner_buffer): return 's'
        if abs(canvas_x - cx1) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'w'
        if abs(canvas_x - cx2) < handle_margin and (cy1 + inner_buffer) < canvas_y < (cy2 - inner_buffer): return 'e'

        return None

    def update_cursor(self, event=None):
        """Changes the mouse cursor based on position relative to selected crop."""
        if self.is_panning or self.is_moving:
            self.canvas.config(cursor="fleur")
            return
        # Don't change cursor if actively drawing or resizing (handled by those modes)
        if self.is_drawing or self.is_resizing:
            return

        new_cursor = "" # Default arrow cursor
        if event: # Only check hover state if event is provided
            canvas_x = self.canvas.canvasx(event.x)
            canvas_y = self.canvas.canvasy(event.y)
            handle = self.get_resize_handle(canvas_x, canvas_y)

            if handle:
                # Map handle to appropriate Tk cursor names
                if handle in ('nw', 'se'): new_cursor = "size_nw_se"
                elif handle in ('ne', 'sw'): new_cursor = "size_ne_sw"
                elif handle in ('n', 's'): new_cursor = "size_ns"
                elif handle in ('e', 'w'): new_cursor = "size_we"
            else:
                # Check if hovering inside the *selected* rectangle for move indication
                if self.selected_crop_id and self.selected_crop_id in self.crops:
                    rect_id = self.crops[self.selected_crop_id]['rect_id']
                    if rect_id in self.canvas.find_all(): # Check valid id
                        cx1, cy1, cx2, cy2 = self.canvas.coords(rect_id)
                        if cx1 < canvas_x < cx2 and cy1 < canvas_y < cy2:
                            new_cursor = "fleur" # Indicate movability

        # Only update if the cursor needs to change
        if self.canvas.cget("cursor") != new_cursor:
             self.canvas.config(cursor=new_cursor)

    # --- Window Resize Handling ---
    def on_window_resize(self, event=None):
        # Optional: Could add logic here to refit the image if the window resizes significantly
        # For now, just let the canvas resize. User can pan/zoom if needed.
        # Example: self.display_image_on_canvas() # This might recalculate display image size
        pass


    # --- Saving Crops ---
    def save_crops(self):
        if not self.original_image or not self.image_path:
            messagebox.showwarning("No Image", "Please select an image first.")
            return
        if not self.crops:
            messagebox.showwarning("No Crops", "Please define at least one crop area.")
            return

        # 3. Create output folder based on image name
        base_name = os.path.splitext(os.path.basename(self.image_path))[0]
        # Create folder in the same directory as the executable/script
        output_dir = os.path.abspath(base_name) # Use absolute path relative to current dir

        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Directory Error", f"Could not create output directory:\n{output_dir}\n{e}")
            return

        saved_count = 0
        error_count = 0

        # Sort crops by name number to save sequentially (Crop_1, Crop_2, ...)
        def get_crop_num(item_tuple):
            # item_tuple is (crop_id, data_dict)
            crop_id, data = item_tuple
            try:
                # Extract number after the last underscore in the 'name' field
                return int(data['name'].split('_')[-1])
            except (ValueError, IndexError):
                return float('inf') # Put improperly named items last

        sorted_crop_items = sorted(self.crops.items(), key=get_crop_num)

        # 3. Save using the new naming pattern
        for i, (crop_id, data) in enumerate(sorted_crop_items, start=1):
            coords = tuple(map(int, data['coords'])) # Ensure integer coords for cropping
            # New filename format: base_name_N.jpg
            filename = f"{base_name}_{i}.jpg"
            filepath = os.path.join(output_dir, filename)

            try:
                cropped_img = self.original_image.crop(coords)
                if cropped_img.mode in ('RGBA', 'P'):
                    cropped_img = cropped_img.convert('RGB')
                cropped_img.save(filepath, "JPEG", quality=95)
                saved_count += 1
                # print(f"Saved: {filepath}") # Optional: print progress to console
            except Exception as e:
                error_count += 1
                print(f"Error saving {filename}: {e}")

        # Show summary message
        # Use the dynamic output directory name in the message
        if error_count == 0:
            messagebox.showinfo("Success", f"Successfully saved {saved_count} crops to the '{base_name}' folder.")
        else:
            messagebox.showwarning("Partial Success", f"Saved {saved_count} crops to '{base_name}'.\nFailed to save {error_count} crops. Check console/log for details.")


# --- Run the Application ---
if __name__ == "__main__":
    app = MultiCropApp()
    app.mainloop()
