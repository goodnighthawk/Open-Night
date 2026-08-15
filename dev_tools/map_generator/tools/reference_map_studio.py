from __future__ import annotations
import csv, tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
ROOT=Path(__file__).resolve().parents[1]
LAYERS=('roads','traffic','terrain','transit','biking')
TRACE={
 'roads':('roads_trace.csv',['road_id','points_image_px','width_class','lane_hint','direction','notes']),
 'traffic':('traffic_trace.csv',['flow_id','points_image_px','priority','relative_density','direction','notes']),
 'terrain':('terrain_trace.csv',['area_id','terrain_type','polygon_image_px','notes']),
 'transit':('transit_trace.csv',['transit_id','mode','points_image_px','station_name','notes']),
 'biking':('biking_trace.csv',['bike_id','facility_type','points_image_px','direction','notes']),
}
class Studio:
 def __init__(self,root):
  self.root=root;root.title('Open Night - Reference Map Trace Studio')
  self.layer=tk.StringVar(value='roads');self.points=[];self.zoom=1.0;self.images={};self.photo=None
  self.idv=tk.StringVar(value='road_001');self.attr1=tk.StringVar(value='primary');self.attr2=tk.StringVar(value='2');self.direction=tk.StringVar(value='both');self.notes=tk.StringVar()
  bar=ttk.Frame(root);bar.pack(fill='x')
  ttk.Label(bar,text='Trace layer:').pack(side='left',pad=4)
  for l in LAYERS: ttk.Radiobutton(bar,text=l.title(),variable=self.layer,value=l,command=self.refresh).pack(side='left')
  ttk.Label(bar,text='ID').pack(side='left',pad=(12,2));ttk.Entry(bar,textvariable=self.idv,width=16).pack(side='left')
  ttk.Label(bar,text='Class/Mode').pack(side='left',pad=(8,2));ttk.Entry(bar,textvariable=self.attr1,width=12).pack(side='left')
  ttk.Label(bar,text='Lanes/Density').pack(side='left',pad=(8,2));ttk.Entry(bar,textvariable=self.attr2,width=8).pack(side='left')
  ttk.Label(bar,text='Direction').pack(side='left',pad=(8,2));ttk.Entry(bar,textvariable=self.direction,width=8).pack(side='left')
  ttk.Button(bar,text='SAVE FEATURE (Enter)',command=self.save).pack(side='right',pad=4);ttk.Button(bar,text='Cancel (Esc)',command=self.cancel).pack(side='right')
  self.canvas=tk.Canvas(root,bg='#111',width=1200,height=700,scrollregion=(0,0,3000,2000));self.canvas.pack(fill='both',expand=True)
  self.canvas.bind('<Button-1>',self.click);self.canvas.bind('<Button-3>',lambda e:self.pop());root.bind('<Return>',lambda e:self.save());root.bind('<Escape>',lambda e:self.cancel());root.bind('<BackSpace>',lambda e:self.pop())
  self.load_images();self.refresh()
 def load_images(self):
  ref=ROOT/'references'/'street_map_reference.png'
  if not ref.exists(): messagebox.showerror('Open Night','Import a street-map reference first.');return
  self.base=Image.open(ref).convert('RGB')
  for l in LAYERS:
   p=ROOT/'references'/'layers'/f'{l}.png'
   if p.exists():self.images[l]=Image.open(p).convert('RGB').resize(self.base.size,Image.Resampling.LANCZOS)
 def refresh(self):
  if not hasattr(self,'base'):return
  img=self.images.get(self.layer.get(),self.base); self.photo=ImageTk.PhotoImage(img)
  self.canvas.delete('all');self.canvas.create_image(0,0,image=self.photo,anchor='nw');self.canvas.config(scrollregion=(0,0,img.width,img.height))
  for x,y in self.points:self.canvas.create_oval(x-4,y-4,x+4,y+4,fill='yellow',outline='black')
  for a,b in zip(self.points,self.points[1:]):self.canvas.create_line(*a,*b,fill='yellow',width=3)
 def click(self,e):
  self.points.append((int(self.canvas.canvasx(e.x)),int(self.canvas.canvasy(e.y))));self.refresh()
 def pop(self):
  if self.points:self.points.pop();self.refresh()
 def cancel(self):self.points=[];self.refresh()
 def _next_id(self):
  base={'roads':'road','traffic':'flow','terrain':'area','transit':'transit','biking':'bike'}[self.layer.get()]
  p=ROOT/'working_reference'/TRACE[self.layer.get()][0];n=max(1,sum(1 for _ in p.open(encoding='utf-8-sig')) if p.exists() else 1);self.idv.set(f'{base}_{n:03d}')
 def save(self):
  layer=self.layer.get();minp=3 if layer=='terrain' else 2
  if len(self.points)<minp:return messagebox.showwarning('Open Night',f'{layer} needs at least {minp} points.')
  fn,fields=TRACE[layer];p=ROOT/'working_reference'/fn;p.parent.mkdir(parents=True,exist_ok=True)
  exists=p.exists() and p.stat().st_size>0
  pts=';'.join(f'{x},{y}' for x,y in self.points)
  if layer=='roads':row={'road_id':self.idv.get(),'points_image_px':pts,'width_class':self.attr1.get() or 'primary','lane_hint':self.attr2.get() or '2','direction':self.direction.get() or 'both','notes':self.notes.get()}
  elif layer=='traffic':row={'flow_id':self.idv.get(),'points_image_px':pts,'priority':self.attr1.get() or 'normal','relative_density':self.attr2.get() or '0.5','direction':self.direction.get() or 'both','notes':self.notes.get()}
  elif layer=='terrain':row={'area_id':self.idv.get(),'terrain_type':self.attr1.get() or 'green','polygon_image_px':pts,'notes':self.notes.get()}
  elif layer=='transit':row={'transit_id':self.idv.get(),'mode':self.attr1.get() or 'rail','points_image_px':pts,'station_name':self.notes.get(),'notes':''}
  else:row={'bike_id':self.idv.get(),'facility_type':self.attr1.get() or 'lane','points_image_px':pts,'direction':self.direction.get() or 'both','notes':self.notes.get()}
  with p.open('a',encoding='utf-8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=fields)
   if not exists:w.writeheader()
   w.writerow(row)
  self.points=[];self._next_id();self.refresh()
if __name__=='__main__':
 r=tk.Tk();Studio(r);r.mainloop()
