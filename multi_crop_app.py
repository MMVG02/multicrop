# -*- coding: utf-8 -*-
"""
Multi Crop App
A simple Windows application to select multiple rectangular regions (crops)
from an image and export them simultaneously.

Features:
- Load various image formats.
- Draw, move, resize multiple crop rectangles.
- Select crops via canvas click or listbox.
- Zoom and Pan the image view.
- Rename individual crops.
- Keyboard shortcuts for common actions (Open, Save, Save As, Delete, Nudge, Resize).
- Save: Creates a subfolder named after the image (next to it) and saves crops
  sequentially (imagename_1.jpg, ...). Remembers this location.
- Save As: Prompts for a folder and saves crops using their current names.
  Updates the default save location for subsequent "Save" clicks.
- Status bar showing coordinates, zoom level, selected crop size, and current action.
- Unsaved changes warning on close or new image load.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, Listbox
import customtkinter as ctk
from PIL import Image, ImageTk
import os
import uuid
import math
import re # For parsing crop numbers and sanitizing filenames

# --- Constants ---
RECT_TAG_PREFIX = "crop_rect_"
DEFAULT_RECT_COLOR = "red"
SELECTED_RECT_COLOR = "blue"
RECT_WIDTH = 2
SELECTED_RECT_WIDTH = 3 # Make selected rectangle thicker
MIN_CROP_SIZE = 10 # Minimum width/height for a crop in image pixels
APP_NAME = "Multi Image Cropper"

# --- Main Application Class ---
class MultiCropApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window Setup ---
        self.title(APP_NAME)
        self.geometry("1100x750") # Initial size
        self.minsize(800, 600)    # Minimum window size
        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        # --- State Variables ---
        self.image_path = None
        self.original_image = None
        self.display_image = None
        self.tk_image = None
        self.canvas_image_id = None
        self.crops = {} # {crop_id: {'coords':(x1,y1,x2,y2), 'name': name, 'rect_id': id, 'order': int}}
        self.selected_crop_id = None
        self.next_crop_order_num = 1
        self.current_save_dir = None # Stores the target dir for the current image session
        self.is_dirty = False # Track unsaved changes

        # Drawing/Editing State
        self.start_x, self.start_y = None, None
        self.current_rect_id = None
        self.is_drawing, self.is_moving, self.is_resizing = False, False, False
        self.resize_handle = None
        self.move_offset_x, self.move_offset_y = 0, 0
        self.start_coords_img = None

        # Zoom/Pan State
        self.zoom_factor = 1.0
        self.pan_start_x, self.pan_start_y = 0, 0
        self.is_panning = False
        self.canvas_offset_x, self.canvas_offset_y = 0, 0

        # --- UI Layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0) # Status bar

        # --- Main Content Frame ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
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
        self.control_frame = ctk.CTkFrame(self.main_frame, width=280)
        self.control_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")
        self.control_frame.grid_propagate(False)
        self.control_frame.grid_columnconfigure(0, weight=1)
        self.control_frame.grid_columnconfigure(1, weight=1)
        self.control_frame.grid_rowconfigure(3, weight=1) # Listbox row grows

        # Control Buttons
        self.btn_select_image = ctk.CTkButton(self.control_frame, text="Select Image (Ctrl+O)", command=self.handle_open)
        self.btn_select_image.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew")

        self.btn_save = ctk.CTkButton(self.control_frame, text="Save (Ctrl+S)", command=self.handle_save, state=tk.DISABLED)
        self.btn_save.grid(row=1, column=0, padx=(10, 5), pady=5, sticky="ew")

        self.btn_save_as = ctk.CTkButton(self.control_frame, text="Save As...", command=self.handle_save_as, state=tk.DISABLED)
        self.btn_save_as.grid(row=1, column=1, padx=(5, 10), pady=5, sticky="ew")

        # Crop List Area
        self.lbl_crop_list = ctk.CTkLabel(self.control_frame, text="Crop List (Double-click to rename):")
        self.lbl_crop_list.grid(row=2, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w")

        self.crop_listbox = Listbox(self.control_frame, bg='white', fg='black',
                                    selectbackground='#CDEAFE', selectforeground='black',
                                    highlightthickness=1, highlightbackground="#CCCCCC",
                                    highlightcolor="#89C4F4", borderwidth=0, exportselection=False)
        self.crop_listbox.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")
        self.crop_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)
        self.crop_listbox.bind("<Double-Button-1>", self.prompt_rename_selected_crop_event)

        # Rename/Delete Buttons
        self.btn_rename_crop = ctk.CTkButton(self.control_frame, text="Rename", command=self.prompt_rename_selected_crop, state=tk.DISABLED)
        self.btn_rename_crop.grid(row=4, column=0, padx=(10, 5), pady=(5, 10), sticky="sew")

        self.btn_delete_crop = ctk.CTkButton(self.control_frame, text="Delete (Del)", command=self.delete_selected_crop, state=tk.DISABLED, fg_color="#F44336", hover_color="#D32F2F")
        self.btn_delete_crop.grid(row=4, column=1, padx=(5, 10), pady=(5, 10), sticky="sew")

        # --- Status Bar ---
        self.status_bar = ctk.CTkFrame(self, height=25, fg_color="gray85")
        self.status_bar.grid(row=1, column=0, sticky="ew", padx=0, pady=(0,0))
        self.status_bar.grid_columnconfigure(0, weight=1); self.status_bar.grid_columnconfigure(1, weight=1); self.status_bar.grid_columnconfigure(2, weight=1)

        self.lbl_status_coords = ctk.CTkLabel(self.status_bar, text=" Img Coords: --- ", text_color="gray30", height=20, anchor="w")
        self.lbl_status_coords.grid(row=0, column=0, sticky="w", padx=(10, 0))
        self.lbl_status_action = ctk.CTkLabel(self.status_bar, text="Ready", text_color="gray30", height=20, anchor="center")
        self.lbl_status_action.grid(row=0, column=1, sticky="ew")
        self.lbl_status_zoom_select = ctk.CTkLabel(self.status_bar, text="Zoom: 100.0% | Sel: --- ", text_color="gray30", height=20, anchor="e")
        self.lbl_status_zoom_select.grid(row=0, column=2, sticky="e", padx=(0, 10))

        # --- Bindings ---
        # Canvas Mouse Bindings
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press); self.canvas.bind("<B1-Motion>", self.on_mouse_drag); self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel); self.canvas.bind("<ButtonPress-4>", lambda e: self.on_mouse_wheel(e, 1)); self.canvas.bind("<ButtonPress-5>", lambda e: self.on_mouse_wheel(e, -1))
        self.canvas.bind("<ButtonPress-2>", self.on_pan_press); self.canvas.bind("<B2-Motion>", self.on_pan_drag); self.canvas.bind("<ButtonRelease-2>", self.on_pan_release)
        self.canvas.bind("<Motion>", self.on_mouse_motion_canvas); self.canvas.bind("<Enter>", self.on_mouse_motion_canvas); self.canvas.bind("<Leave>", self.clear_status_coords)

        # Global Keyboard Bindings
        self.bind_all("<Control-o>", self.handle_open_event); self.bind_all("<Control-O>", self.handle_open_event)
        self.bind_all("<Control-s>", self.handle_save_event); self.bind_all("<Control-S>", self.handle_save_event)
        self.bind_all("<Delete>", lambda e: self.delete_selected_crop_event(e)) # Corrected
        # Nudge/Resize Bindings
        self.bind_all("<Left>", lambda e: self.handle_nudge(-1, 0)); self.bind_all("<Right>", lambda e: self.handle_nudge(1, 0))
        self.bind_all("<Up>", lambda e: self.handle_nudge(0, -1)); self.bind_all("<Down>", lambda e: self.handle_nudge(0, 1))
        self.bind_all("<Shift-Left>", lambda e: self.handle_resize_key(-1, 0, 'w')); self.bind_all("<Shift-Right>", lambda e: self.handle_resize_key(1, 0, 'e'))
        self.bind_all("<Shift-Up>", lambda e: self.handle_resize_key(0, -1, 'n')); self.bind_all("<Shift-Down>", lambda e: self.handle_resize_key(0, 1, 's'))

        # Window Events
        self.bind("<Configure>", self.on_window_resize)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Initial status bar update
        self.update_status_bar()

    # --- Unsaved Changes Handling ---
    def set_dirty(self, dirty_state=True):
        if self.is_dirty != dirty_state:
            self.is_dirty = dirty_state
            title = APP_NAME
            if self.is_dirty: title += " *"
            self.title(title)

    def check_unsaved_changes(self):
        if not self.is_dirty: return True
        response = messagebox.askyesnocancel("Unsaved Changes", "You have unsaved crops. Save before proceeding?", icon=messagebox.WARNING, parent=self)
        if response is True: self.handle_save(); return not self.is_dirty
        elif response is False: return True
        else: return False

    def on_closing(self):
        if self.check_unsaved_changes(): self.destroy()

    # --- Status Bar Update ---
    def update_status_bar(self, action_text=None, coords_text=None, selection_text=None):
        current_action = self.lbl_status_action.cget("text"); current_coords = self.lbl_status_coords.cget("text"); current_zoom_select = self.lbl_status_zoom_select.cget("text")
        parts = current_zoom_select.split('|', 1); current_select_info = parts[1].strip() if len(parts) > 1 else "Sel: ---"
        new_action = action_text if action_text is not None else current_action; new_coords = coords_text if coords_text is not None else current_coords
        new_select_info = selection_text if selection_text is not None else current_select_info; new_zoom = f"Zoom: {self.zoom_factor:.1%}"
        self.lbl_status_action.configure(text=new_action); self.lbl_status_coords.configure(text=new_coords); self.lbl_status_zoom_select.configure(text=f"{new_zoom} | {new_select_info}")

    def clear_status_coords(self, event=None): self.update_status_bar(coords_text=" Img Coords: --- ")

    def on_mouse_motion_canvas(self, event):
        coords_text = " Img Coords: --- "; img_w, img_h = (0,0)
        if self.original_image: img_w, img_h = self.original_image.size
        canvas_x, canvas_y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y); img_x, img_y = self.canvas_to_image_coords(canvas_x, canvas_y)
        if img_x is not None and img_y is not None: clamped_x, clamped_y = max(0, min(img_x, img_w)), max(0, min(img_y, img_h)); coords_text = f" Img Coords: {int(clamped_x):>4}, {int(clamped_y):>4}"
        self.update_status_bar(coords_text=coords_text); self.update_cursor(event)

    def update_status_bar_selection(self):
        selection_text = " Sel: --- "
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            coords = self.crops[self.selected_crop_id].get('coords')
            if coords and len(coords) == 4: w, h = coords[2] - coords[0], coords[3] - coords[1]; selection_text = f" Sel: {max(0, int(w))}x{max(0, int(h))} px"
        self.update_status_bar(selection_text=selection_text)

    # --- Shortcut Handlers ---
    def handle_open_event(self, event=None): self.handle_open(); return "break"
    def handle_open(self): self.select_image()
    def handle_save_event(self, event=None): self.handle_save(); return "break"

    def handle_save(self):
        if not self._check_save_preconditions(): return
        target_dir = self.current_save_dir
        if not target_dir:
            try:
                if not self.image_path: raise ValueError("Image path not set")
                img_dir = os.path.dirname(self.image_path); base_name = os.path.splitext(os.path.basename(self.image_path))[0]
                if not base_name: raise ValueError("Could not determine base name")
                target_dir = os.path.join(img_dir, base_name); os.makedirs(target_dir, exist_ok=True); self.current_save_dir = target_dir
            except Exception as e: messagebox.showerror("Directory Error", f"Could not determine/create default save directory:\n{e}", parent=self); self.update_status_bar(action_text="Save Failed (Dir Error)"); return
        self._perform_save(target_dir=target_dir, use_sequential_naming=True)

    def handle_save_as(self):
        if not self._check_save_preconditions(): return
        initial_dir = self.current_save_dir
        if not initial_dir and self.image_path:
            try: img_dir = os.path.dirname(self.image_path); base_name = os.path.splitext(os.path.basename(self.image_path))[0]; initial_dir = os.path.join(img_dir, base_name)
            except: pass
        output_dir = filedialog.askdirectory(parent=self, title="Select Folder to Save Cropped Images", initialdir=initial_dir)
        if not output_dir: self.update_status_bar(action_text="Save As Cancelled"); return
        self.current_save_dir = output_dir; self._perform_save(target_dir=output_dir, use_sequential_naming=False)

    def _check_save_preconditions(self):
        if not self.original_image or not self.image_path: messagebox.showwarning("Save Error", "No image loaded.", parent=self); return False
        if not self.crops: messagebox.showwarning("Save Error", "No crops defined.", parent=self); return False
        return True

    def handle_nudge(self, dx_img, dy_img):
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            cid=self.selected_crop_id; c=self.crops[cid].get('coords');
            if not c: return
            nx1,ny1,nx2,ny2=c[0]+dx_img,c[1]+dy_img,c[2]+dx_img,c[3]+dy_img
            if self.update_crop_coords(cid,(nx1,ny1,nx2,ny2)): self.redraw_all_crops();self.update_status_bar(action_text="Nudged");self.update_status_bar_selection()

    def handle_resize_key(self, dx_img, dy_img, hdir):
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            cid=self.selected_crop_id; c=self.crops[cid].get('coords');
            if not c: return
            nx1,ny1,nx2,ny2=c[0],c[1],c[2],c[3]
            if 'n' in hdir: ny1+=dy_img;
            if 's' in hdir: ny2+=dy_img;
            if 'w' in hdir: nx1+=dx_img;
            if 'e' in hdir: nx2+=dx_img;
            if self.update_crop_coords(cid,(nx1,ny1,nx2,ny2)): self.redraw_all_crops();self.update_status_bar(action_text="Resized");self.update_status_bar_selection()

    def delete_selected_crop_event(self, event=None):
        self.delete_selected_crop()
        return "break"

    # --- Image Handling ---
    def select_image(self):
        if not self.check_unsaved_changes(): return
        path = filedialog.askopenfilename(title="Select Image File", filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.tiff *.webp"), ("All", "*.*")])
        if not path: self.update_status_bar(action_text="Image Selection Cancelled"); return
        self.update_status_bar(action_text="Loading..."); self.update_idletasks()
        try:
            img = Image.open(path)
            if img.mode == 'CMYK': img = img.convert('RGB')
            elif img.mode == 'P': img = img.convert('RGBA')
            self.image_path = path; self.original_image = img
            self.update_idletasks()
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            if cw <= 1: cw = self.canvas.winfo_reqwidth()
            if ch <= 1: ch = self.canvas.winfo_reqheight()
            iw, ih = self.original_image.size
            if iw <= 0 or ih <= 0: raise ValueError("Invalid image dimensions")
            zh, zv = (cw / iw) if iw > 0 else 1, (ch / ih) if ih > 0 else 1
            iz = min(zh, zv, 1.0); pf = 0.98; self.zoom_factor = iz * pf
            dw, dh = iw * self.zoom_factor, ih * self.zoom_factor
            self.canvas_offset_x, self.canvas_offset_y = math.ceil((cw - dw) / 2), math.ceil((ch - dh) / 2)
            self.clear_crops_and_list(); self.next_crop_order_num = 1; self.current_save_dir = None
            self.display_image_on_canvas()
            self.btn_save.configure(state=tk.DISABLED); self.btn_save_as.configure(state=tk.DISABLED)
            self.set_dirty(False); self.update_status_bar(action_text="Image Loaded")
        except FileNotFoundError: messagebox.showerror("Error", f"File not found:\n{path}", parent=self); self.update_status_bar(action_text="Error: Not Found")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open/process image:\n{e}", parent=self)
            self.image_path=None; self.original_image=None; self.clear_crops_and_list(); self.canvas.delete("all"); self.tk_image=None; self.display_image=None
            self.btn_save.configure(state=tk.DISABLED); self.btn_save_as.configure(state=tk.DISABLED); self.set_dirty(False); self.current_save_dir = None
            self.update_status_bar(action_text="Error Loading")

    # --- Display, Clear, Coord Conversion ---
    def display_image_on_canvas(self):
        if not self.original_image: self.canvas.delete("all"); return
        dw,dh = max(1,int(self.original_image.width*self.zoom_factor)), max(1,int(self.original_image.height*self.zoom_factor))
        try: self.display_image=self.original_image.resize((dw,dh),Image.Resampling.LANCZOS); self.tk_image=ImageTk.PhotoImage(self.display_image)
        except Exception as e: print(f"Display err:{e}"); self.canvas.delete("all"); self.update_status_bar(action_text="Display Error"); return
        self.canvas.delete("all"); x0,y0=int(round(self.canvas_offset_x)),int(round(self.canvas_offset_y))
        self.canvas_image_id=self.canvas.create_image(x0,y0,anchor=tk.NW,image=self.tk_image,tags="image"); self.redraw_all_crops()

    def clear_crops_and_list(self):
        self.canvas.delete("crop_rect"); self.crops.clear(); self.crop_listbox.delete(0,tk.END); self.selected_crop_id=None
        self.btn_delete_crop.configure(state=tk.DISABLED); self.btn_rename_crop.configure(state=tk.DISABLED)
        self.btn_save.configure(state=tk.DISABLED); self.btn_save_as.configure(state=tk.DISABLED)

    def canvas_to_image_coords(self, cx, cy):
        if not self.original_image or self.zoom_factor<=0: return None,None
        return (cx-self.canvas_offset_x)/self.zoom_factor, (cy-self.canvas_offset_y)/self.zoom_factor
    def image_to_canvas_coords(self, ix, iy):
        if not self.original_image: return None,None
        return (ix*self.zoom_factor)+self.canvas_offset_x, (iy*self.zoom_factor)+self.canvas_offset_y

    # --- Crop Handling ---
    def add_crop(self, x1i, y1i, x2i, y2i):
        if not self.original_image: return
        iw,ih=self.original_image.size; x1i,y1i=max(0,min(x1i,iw)),max(0,min(y1i,ih)); x2i,y2i=max(0,min(x2i,iw)),max(0,min(y2i,ih))
        c=(min(x1i,x2i),min(y1i,y2i),max(x1i,x2i),max(y1i,y2i))
        if(c[2]-c[0])<MIN_CROP_SIZE or(c[3]-c[1])<MIN_CROP_SIZE:
            if self.current_rect_id and self.current_rect_id in self.canvas.find_withtag("temp_rect"): self.canvas.delete(self.current_rect_id)
            self.current_rect_id=None;self.update_status_bar(action_text="Crop Too Small");return
        cid=str(uuid.uuid4());cname=f"Crop_{self.next_crop_order_num}";cono=self.next_crop_order_num;self.next_crop_order_num+=1
        cx1,cy1=self.image_to_canvas_coords(c[0],c[1]);cx2,cy2=self.image_to_canvas_coords(c[2],c[3])
        if cx1 is None: print("Err:Coord conv fail");self.update_status_bar(action_text="Err Add");return
        rid=self.canvas.create_rectangle(cx1,cy1,cx2,cy2,outline=SELECTED_RECT_COLOR,width=SELECTED_RECT_WIDTH,tags=(RECT_TAG_PREFIX+cid,"crop_rect"))
        self.crops[cid]={'coords':c,'name':cname,'rect_id':rid,'order':cono}
        self.crop_listbox.insert(tk.END,cname);self.crop_listbox.selection_clear(0,tk.END);self.crop_listbox.selection_set(tk.END);self.crop_listbox.activate(tk.END);self.crop_listbox.see(tk.END)
        self.select_crop(cid,from_listbox=False);self.btn_save.configure(state=tk.NORMAL);self.btn_save_as.configure(state=tk.NORMAL);self.set_dirty();self.update_status_bar(action_text="Crop Added")

    def select_crop(self, cid, from_lb=True):
        if self.selected_crop_id==cid and cid is not None: self.update_status_bar_selection(); return
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            pd=self.crops[self.selected_crop_id];pri=pd.get('rect_id');
            if pri and pri in self.canvas.find_withtag(pri): self.canvas.itemconfig(pri,outline=DEFAULT_RECT_COLOR,width=RECT_WIDTH)
        self.selected_crop_id=cid
        if cid and cid in self.crops:
            d=self.crops[cid];rid=d.get('rect_id');
            if rid and rid in self.canvas.find_withtag(rid):
                 self.canvas.itemconfig(rid,outline=SELECTED_RECT_COLOR,width=SELECTED_RECT_WIDTH);self.canvas.tag_raise(rid)
                 self.btn_delete_crop.configure(state=tk.NORMAL);self.btn_rename_crop.configure(state=tk.NORMAL)
                 if not from_lb:
                     idx=-1;
                     for i in range(self.crop_listbox.size()):
                         if self.crop_listbox.get(i)==d.get('name'): idx=i;break
                     if idx!=-1: self.crop_listbox.selection_clear(0,tk.END);self.crop_listbox.selection_set(idx);self.crop_listbox.activate(idx);self.crop_listbox.see(idx)
            else: self.selected_crop_id=None;self.btn_delete_crop.configure(state=tk.DISABLED);self.btn_rename_crop.configure(state=tk.DISABLED)
        else: # Deselection
            self.selected_crop_id=None;
            if not from_lb: self.crop_listbox.selection_clear(0,tk.END) # Corrected indentation here
            self.btn_delete_crop.configure(state=tk.DISABLED);self.btn_rename_crop.configure(state=tk.DISABLED)
        self.update_status_bar_selection()

    def update_crop_coords(self, cid, ncoords):
        if cid in self.crops and self.original_image:
            iw,ih=self.original_image.size;x1,y1,x2,y2=ncoords;x1,y1=max(0,min(x1,iw)),max(0,min(y1,ih));x2,y2=max(0,min(x2,iw)),max(0,min(y2,ih))
            fx1,fy1,fx2,fy2=min(x1,x2),min(y1,y2),max(x1,x2),max(y1,y2)
            if(fx2-fx1)<MIN_CROP_SIZE or(fy2-fy1)<MIN_CROP_SIZE: return False
            nct=(fx1,fy1,fx2,fy2);
            if self.crops[cid]['coords']!=nct: self.crops[cid]['coords']=nct;self.set_dirty();return True
            else: return True
        return False

    def redraw_all_crops(self):
        aci=self.canvas.find_all()
        for cid,d in self.crops.items():
            # CORRECTED SYNTAX HERE:
            c=d.get('coords'); rid=d.get('rect_id')
            if not c or len(c)!=4: continue
            # Rest of the assignments and check moved to next line
            ix1,iy1,ix2,iy2=c; cx1,cy1=self.image_to_canvas_coords(ix1,iy1); cx2,cy2=self.image_to_canvas_coords(ix2,iy2)
            if cx1 is None: continue # Check moved here
            sel=(cid==self.selected_crop_id);clr=SELECTED_RECT_COLOR if sel else DEFAULT_RECT_COLOR;wid=SELECTED_RECT_WIDTH if sel else RECT_WIDTH;tgs=(RECT_TAG_PREFIX+cid,"crop_rect")
            if rid and rid in aci: self.canvas.coords(rid,cx1,cy1,cx2,cy2);self.canvas.itemconfig(rid,outline=clr,width=wid,tags=tgs)
            else: nrid=self.canvas.create_rectangle(cx1,cy1,cx2,cy2,outline=clr,width=wid,tags=tgs);self.crops[cid]['rect_id']=nrid
        if self.selected_crop_id and self.selected_crop_id in self.crops:
            srid=self.crops[self.selected_crop_id].get('rect_id');
            if srid and srid in self.canvas.find_all():self.canvas.tag_raise(srid)
        self.update_status_bar_selection()

    def delete_selected_crop(self):
        if not self.selected_crop_id or self.selected_crop_id not in self.crops: return
        cid=self.selected_crop_id;d=self.crops[cid];rid=d.get('rect_id');cn=d.get('name')
        if rid and rid in self.canvas.find_all():self.canvas.delete(rid)
        idx=-1;
        if cn:
            for i in range(self.crop_listbox.size()):
                if self.crop_listbox.get(i)==cn:idx=i;break
        del self.crops[cid];
        if idx!=-1:self.crop_listbox.delete(idx)
        self.selected_crop_id=None;self.btn_delete_crop.configure(state=tk.DISABLED);self.btn_rename_crop.configure(state=tk.DISABLED)
        if not self.crops: self.btn_save.configure(state=tk.DISABLED);self.btn_save_as.configure(state=tk.DISABLED)
        self.set_dirty();self.update_status_bar(action_text="Crop Deleted")
        if self.crop_listbox.size()>0:
            nidx=max(0,idx-1);
            if idx==0 or idx==-1:nidx=0
            if nidx>=self.crop_listbox.size():nidx=self.crop_listbox.size()-1
            self.crop_listbox.selection_set(nidx);self.on_listbox_select()
        else: self.crop_listbox.selection_clear(0,tk.END);self.select_crop(None,from_listbox=False)

    def prompt_rename_selected_crop_event(self,event=None): self.prompt_rename_selected_crop()
    def prompt_rename_selected_crop(self):
        if not self.selected_crop_id or self.selected_crop_id not in self.crops: messagebox.showwarning("Rename Err","Select crop",parent=self);return
        cid=self.selected_crop_id;cn=self.crops[cid].get('name','')
        dlg=ctk.CTkInputDialog(text=f"New name for '{cn}':",title="Rename",entry_fg_color="white",entry_text_color="black");dlg.geometry(f"+{self.winfo_x()+200}+{self.winfo_y()+200}")
        nnr=dlg.get_input();
        if nnr is None or not nnr.strip(): self.update_status_bar(action_text="Rename Cancel");return
        nn=nnr.strip();
        for c,d in self.crops.items():
            if c!=cid and d.get('name')==nn: messagebox.showerror("Rename Err",f"Name '{nn}' exists",parent=self);return
        self.crops[cid]['name']=nn;idx=-1;
        for i in range(self.crop_listbox.size()):
            if self.crop_listbox.get(i)==cn:idx=i;break
        if idx!=-1: self.crop_listbox.delete(idx);self.crop_listbox.insert(idx,nn);self.crop_listbox.selection_set(idx);self.crop_listbox.activate(idx)
        self.set_dirty();self.update_status_bar(action_text="Renamed")

    # --- Mouse Events ---
    def on_mouse_press(self, e):
        self.canvas.focus_set(); cx,cy=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y); atxt="Ready"
        h=self.get_resize_handle(cx,cy);
        if h and self.selected_crop_id: self.is_resizing=True;self.resize_handle=h;self.start_x,self.start_y=cx,cy;self.start_coords_img=self.crops[self.selected_crop_id].get('coords');atxt="Resizing";self.update_status_bar(action_text=atxt);return
        ov=self.canvas.find_overlapping(cx-1,cy-1,cx+1,cy+1);ccid=None;
        for iid in reversed(ov):
            t=self.canvas.gettags(iid);
            if t and t[0].startswith(RECT_TAG_PREFIX)and"crop_rect"in t:cid=t[0][len(RECT_TAG_PREFIX):];if cid in self.crops:ccid=cid;break
        if ccid: self.select_crop(ccid);self.is_moving=True;rc=self.canvas.coords(self.crops[ccid]['rect_id']);self.move_offset_x,self.move_offset_y=cx-rc[0],cy-rc[1];self.start_coords_img=self.crops[ccid].get('coords');atxt="Moving";self.update_status_bar(action_text=atxt);return
        if self.original_image: self.is_drawing=True;self.start_x,self.start_y=cx,cy;self.current_rect_id=self.canvas.create_rectangle(cx,cy,cx,cy,outline=SELECTED_RECT_COLOR,width=RECT_WIDTH,dash=(4,4),tags=("temp_rect",));self.select_crop(None);atxt="Drawing";self.update_status_bar(action_text=atxt)

    def on_mouse_drag(self, e):
        cx,cy=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y);
        if self.is_drawing and self.current_rect_id: self.canvas.coords(self.current_rect_id,self.start_x,self.start_y,cx,cy)
        elif self.is_moving and self.selected_crop_id:
            cid=self.selected_crop_id;rid=self.crops[cid]['rect_id'];ncx1=cx-self.move_offset_x;ncy1=cy-self.move_offset_y;cco=self.canvas.coords(rid);w,h=cco[2]-cco[0],cco[3]-cco[1];ncx2,ncy2=ncx1+w,ncy1+h
            ix1,iy1=self.canvas_to_image_coords(ncx1,ncy1);ix2,iy2=self.canvas_to_image_coords(ncx2,ncy2);
            if ix1 is not None and self.update_crop_coords(cid,(ix1,iy1,ix2,iy2)): self.redraw_all_crops();self.update_status_bar_selection()
        elif self.is_resizing and self.selected_crop_id and self.resize_handle and self.start_coords_img:
            cid=self.selected_crop_id;oxi1,oyi1,oxi2,oyi2=self.start_coords_img;cix,ciy=self.canvas_to_image_coords(cx,cy);sixc,siyc=self.canvas_to_image_coords(self.start_x,self.start_y);
            if cix is None or sixc is None: return
            dxi,dyi=cix-sixc,ciy-siyc;nx1,ny1,nx2,ny2=oxi1,oyi1,oxi2,oyi2
            if'n'in self.resize_handle:ny1+=dyi;
            if's'in self.resize_handle:ny2+=dyi;
            if'w'in self.resize_handle:nx1+=dxi;
            if'e'in self.resize_handle:nx2+=dxi;
            if self.update_crop_coords(cid,(nx1,ny1,nx2,ny2)): self.redraw_all_crops();self.update_status_bar_selection()

    def on_mouse_release(self, e):
        if self.is_drawing and self.current_rect_id:
            cx,cy=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y);
            if self.current_rect_id in self.canvas.find_withtag("temp_rect"):self.canvas.delete(self.current_rect_id)
            self.current_rect_id=None;ix1,iy1=self.canvas_to_image_coords(self.start_x,self.start_y);ix2,iy2=self.canvas_to_image_coords(cx,cy);
            if ix1 is not None and iy1 is not None and ix2 is not None and iy2 is not None: self.add_crop(ix1,iy1,ix2,iy2)
            else: print("Fail add crop");self.update_status_bar(action_text="Err Add")
        self.is_drawing,self.is_moving,self.is_resizing=False,False,False;self.resize_handle=None;self.start_x,self.start_y=None,None;self.start_coords_img=None;self.update_cursor(e);
        if not(self.is_drawing and self.current_rect_id is None):self.update_status_bar(action_text="Ready")


    # --- Zoom/Pan ---
    def on_mouse_wheel(self, e, direction=None):
        if not self.original_image:return;delta=0;
        if direction:delta=direction;
        elif e.num==5 or e.delta<0:delta=-1;
        elif e.num==4 or e.delta>0:delta=1;
        else:return
        zinc,zmin,zmax=1.1,0.01,25.0;cx,cy=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y);ixb,iyb=self.canvas_to_image_coords(cx,cy);if ixb is None:return
        nz=self.zoom_factor*zinc if delta>0 else self.zoom_factor/zinc;nz=max(zmin,min(zmax,nz));if abs(nz-self.zoom_factor)<0.0001:return
        self.zoom_factor=nz;self.canvas_offset_x=cx-(ixb*nz);self.canvas_offset_y=cy-(iyb*nz);self.display_image_on_canvas();self.update_status_bar(action_text=f"Zoom {('In' if delta>0 else 'Out')}")
    def on_pan_press(self, e):
        if not self.original_image:return;self.is_panning=True;self.pan_start_x,self.pan_start_y=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y);self.canvas.config(cursor="fleur");self.update_status_bar(action_text="Panning...")
    def on_pan_drag(self, e):
        if not self.is_panning or not self.original_image:return;cx,cy=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y);dx,dy=cx-self.pan_start_x,cy-self.pan_start_y;self.canvas_offset_x+=dx;self.canvas_offset_y+=dy;self.canvas.move("all",dx,dy);self.pan_start_x,self.pan_start_y=cx,cy
    def on_pan_release(self, e): self.is_panning=False;self.update_cursor(e);self.update_status_bar(action_text="Ready")

    # --- Listbox Selection ---
    def on_listbox_select(self, e=None):
        sel=self.crop_listbox.curselection();sid=None;
        if sel:sidx=sel[0];sname=self.crop_listbox.get(sidx);
              for cid,d in self.crops.items():
                  if d.get('name')==sname:sid=cid;break
        self.select_crop(sid,from_listbox=True)

    # --- Resizing Helpers & Cursor ---
    def get_resize_handle(self, cx, cy):
        if not self.selected_crop_id or self.selected_crop_id not in self.crops:return None
        rid=self.crops[self.selected_crop_id].get('rect_id');if not rid or rid not in self.canvas.find_all():return None
        c1,r1,c2,r2=self.canvas.coords(rid);m=8;
        if abs(cx-c1)<m and abs(cy-r1)<m: return 'nw';
        if abs(cx-c2)<m and abs(cy-r1)<m: return 'ne';
        if abs(cx-c1)<m and abs(cy-r2)<m: return 'sw';
        if abs(cx-c2)<m and abs(cy-r2)<m: return 'se';
        ib=m/2;
        if abs(cy-r1)<m and(c1+ib)<cx<(c2-ib): return 'n';
        if abs(cy-r2)<m and(c1+ib)<cx<(c2-ib): return 's';
        if abs(cx-c1)<m and(r1+ib)<cy<(r2-ib): return 'w';
        if abs(cx-c2)<m and(r1+ib)<cy<(r2-ib): return 'e';
        return None
    def update_cursor(self, e=None):
        nc="";
        if self.is_panning or self.is_moving: nc="fleur"
        elif self.is_resizing:
            h=self.resize_handle;
            if h in('nw','se'):nc="size_nw_se";elif h in('ne','sw'):nc="size_ne_sw";elif h in('n','s'):nc="size_ns";elif h in('e','w'):nc="size_we";
        elif self.is_drawing: nc="crosshair"
        else: # Hover state
            if e: cx,cy=self.canvas.canvasx(e.x),self.canvas.canvasy(e.y);h=self.get_resize_handle(cx,cy);
                  if h:
                      if h in('nw','se'):nc="size_nw_se";elif h in('ne','sw'):nc="size_ne_sw";elif h in('n','s'):nc="size_ns";elif h in('e','w'):nc="size_we";
                  else: # Hover inside selected
                      if self.selected_crop_id and self.selected_crop_id in self.crops:
                          rid=self.crops[self.selected_crop_id].get('rect_id');
                          if rid and rid in self.canvas.find_all(): c1,r1,c2,r2=self.canvas.coords(rid);m=1;if(c1+m)<cx<(c2-m)and(r1+m)<cy<(r2-m): nc="fleur"
        if self.canvas.cget("cursor")!=nc: self.canvas.config(cursor=nc)

    # --- Window Resize Handling ---
    def on_window_resize(self, event=None): pass

    # --- Core Saving Logic ---
    def _perform_save(self, target_dir, use_sequential_naming):
        if not self.original_image or not self.image_path: print("Save Err: No img"); return
        self.update_status_bar(action_text="Saving..."); self.update_idletasks(); sc,ec=0,0; ems=[]
        def get_co(it): return it[1].get('order', float('inf'))
        sci=sorted(self.crops.items(), key=get_co); bn=""
        if use_sequential_naming: bn=os.path.splitext(os.path.basename(self.image_path))[0]
        for i,(cid,d)in enumerate(sci):
            coords=d.get('coords');cn=d.get('name',f'Un_{i+1}');
            if not coords: ec+=1;ems.append(f"Skip '{cn}':Bad data");continue
            if use_sequential_naming: fn=f"{bn}_{i+1}.jpg"
            else: scn=re.sub(r'[\\/*?:"<>|]','_',cn).rstrip('. ');if not scn:scn=f"Crop_{d.get('order',i+1)}";fn=f"{scn}.jpg"
            fp=os.path.join(target_dir,fn);ico=tuple(map(int,coords));
            try:
                cr_img=self.original_image.crop(ico);
                if cr_img.mode in('RGBA','P','LA'): bg=Image.new("RGB",cr_img.size,(255,255,255));bg.paste(cr_img,mask=cr_img.split()[-1]if'A'in cr_img.mode else None);cr_img=bg
                elif cr_img.mode!='RGB': cr_img=cr_img.convert('RGB')
                cr_img.save(fp,"JPEG",quality=95,optimize=True); sc+=1
            except Exception as e: ec+=1;emsg=f"Err '{fn}':{e}";print(emsg);ems.append(emsg)
        if ec==0: self.set_dirty(False);messagebox.showinfo("Success",f"Saved {sc} crops:\n{target_dir}",parent=self);self.update_status_bar(action_text="Saved OK")
        else: esum="\n - ".join(ems[:3]);if len(ems)>3:esum+="\n (...more)";messagebox.showwarning("Partial OK",f"Saved {sc}. Failed {ec}:\n{target_dir}\n\nErrors:\n - {esum}",parent=self);self.update_status_bar(action_text="Saved (errors)")

# --- Run the Application ---
if __name__ == "__main__":
    try: from ctypes import windll; windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    app = MultiCropApp()
    app.mainloop()
