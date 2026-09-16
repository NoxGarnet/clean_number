#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compose optional diagnostic figures for compression or flexural runs."""

import os, logging, zlib, numpy as np
import matplotlib as mpl; mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams
from filename_parser import get_group_label, get_group_color, get_group_linestyle

log = logging.getLogger("figure")
rcParams.update({"font.family":"serif","font.serif":["Times New Roman"],"font.size":11,"axes.labelsize":13,"axes.titlesize":13,"xtick.labelsize":11,"ytick.labelsize":11,"legend.fontsize":10,"figure.dpi":300,"savefig.dpi":300,"savefig.bbox":"tight"})

def _number(value):
    return f"{value:.2f}" if value is not None and np.isfinite(value) else "N/A"

def _get_flexural(r):
    if isinstance(r, dict): return r.get("flexural", False)
    return bool(r)

def _get_axis_labels(r):
    fx = _get_flexural(r)
    return ("Displacement (mm)", "Stress (MPa)") if fx else ("Strain (%)", "Stress (MPa)")

def _result_style(r):
    configured = r.get("style", {}) or {}
    if configured.get("color"):
        return configured["color"], configured.get("linestyle", "-")
    palette = ["#111111", "#555555", "#888888", "#bbbbbb"]
    index = zlib.crc32(r["group_key"].encode("utf-8")) % len(palette)
    return palette[index], ["-", "--", "-.", ":"][index]

def _style_ax(ax, r=None):
    ax.tick_params(direction="in",length=5,width=0.8,top=True,right=True)
    for s in ax.spines.values(): s.set_linewidth(0.8)
    xl,yl = _get_axis_labels(r) if r else ("Strain (%)","Stress (MPa)")
    ax.set_xlabel(xl); ax.set_ylabel(yl)

def plot_single_group(r, output_dir, shading=True, figures_dir=None):
    sd = figures_dir or output_dir; gk=r["group_key"]; lbl=r.get("group_label", get_group_label(gk)); c,_=_result_style(r)
    fig,ax = plt.subplots(figsize=(6,5)); x=r["x_grid"]; m=r["stress_mean"]; s=r["stress_std"]
    if x is None or m is None:
        ax.text(0.5,0.5,"No valid data",transform=ax.transAxes,ha="center")
    else:
        if shading and s is not None: ax.fill_between(x,m-s,m+s,color=c,alpha=0.15,label="+-1 SD")
        ax.plot(x,m,color=c,lw=1.5,label=f"{lbl} (n={r['n']})")
    _style_ax(ax,r); ax.set_title(lbl,fontsize=12)
    if r["strength_mean"] is not None:
        txt = f"$\\sigma_{{\\mathrm{{peak}}}}$ = {_number(r['strength_mean'])} +- {_number(r['strength_std'])} MPa"
        if not _get_flexural(r):
            txt += f"\n$ = {_number(r['modulus_mean'])} +- {_number(r['modulus_std'])} GPa"
        ax.text(0.65*x[-1],0.85*np.nanmax(m),txt,fontsize=9,va="top",bbox=dict(boxstyle="round",facecolor="white",edgecolor="gray",alpha=0.85))
    ax.legend(loc="lower right",frameon=True,edgecolor="gray"); ax.set_xlim(left=0); ax.set_ylim(bottom=0)
    os.makedirs(sd,exist_ok=True)
    sfx = "_flexural" if _get_flexural(r) else ""
    p = os.path.join(sd,f"mean_{gk}_stress_strain{sfx}.png")
    fig.savefig(p,dpi=300); plt.close(fig); log.info("  单组曲线: %s",p); return p

def plot_comparison(groups_results, output_dir, filename="comparison_stress_strain.png", figures_dir=None):
    sd = figures_dir or output_dir; fig,ax = plt.subplots(figsize=(6,5))
    fx = any(_get_flexural(r) for r in groups_results if r.get("n",0)>0)
    for r in groups_results:
        if r["n"]==0: continue
        gk=r["group_key"]; x=r["x_grid"]; m=r["stress_mean"]; s=r["stress_std"]
        c,ls = _result_style(r)
        lbl = r.get("group_label", get_group_label(gk))
        if x is None or m is None: continue
        if s is not None: ax.fill_between(x,m-s,m+s,color=c,alpha=0.1)
        ax.plot(x,m,color=c,lw=1.5,linestyle=ls,label=f"{lbl} (n={r['n']})")
    _style_ax(ax,{"flexural":fx})
    t = "Flexural Stress-Displacement Curves" if fx else "Compressive Stress-Strain Curves"
    ax.set_title(t,fontsize=12); ax.legend(loc="lower right",frameon=True,edgecolor="gray")
    ax.set_xlim(left=0); ax.set_ylim(bottom=0)
    os.makedirs(sd,exist_ok=True); p=os.path.join(sd,filename)
    fig.savefig(p,dpi=300); plt.close(fig); log.info("对比曲线: %s",p); return p

def plot_multi_panel(groups_results, output_dir, layout=(2,2), filename="multi_panel_stress_strain.png", figures_dir=None):
    sd=figures_dir or output_dir; nr,nc=layout
    fig,axes=plt.subplots(nr,nc,figsize=(6*nc,5*nr))
    if nr==1 and nc==1: axes=np.array([axes])
    af=axes.flatten(); vr=[r for r in groups_results if r["n"]>0]
    fx=any(_get_flexural(r) for r in vr)
    for idx,ax in enumerate(af):
        if idx<len(vr):
            r=vr[idx]; gk=r["group_key"]; x=r["x_grid"]; m=r["stress_mean"]; s=r["stress_std"]
            c,_ = _result_style(r)
            lbl = r.get("group_label", get_group_label(gk))
            if x is not None and m is not None:
                if s is not None: ax.fill_between(x,m-s,m+s,color=c,alpha=0.15)
                ax.plot(x,m,color=c,lw=1.5)
            ax.tick_params(direction="in",length=5,width=0.8,top=True,right=True)
            for sp in ax.spines.values(): sp.set_linewidth(0.8)
            xl,yl=_get_axis_labels({"flexural":fx}); ax.set_xlabel(xl); ax.set_ylabel(yl)
            ax.set_title(f"({chr(97+idx)}) {lbl}",fontsize=12); ax.set_xlim(left=0); ax.set_ylim(bottom=0)
            if r["strength_mean"] is not None:
                txt=f"$\\sigma_{{p}}$={_number(r['strength_mean'])}+-{_number(r['strength_std'])} MPa"
                if not fx: txt+=f"\n$={_number(r['modulus_mean'])}+-{_number(r['modulus_std'])} GPa"
                ax.text(0.6*x[-1],0.85*np.nanmax(m),txt,fontsize=8,va="top",bbox=dict(boxstyle="round",facecolor="white",edgecolor="gray",alpha=0.85))
        else: ax.axis("off")
    plt.tight_layout(); os.makedirs(sd,exist_ok=True); p=os.path.join(sd,filename)
    fig.savefig(p,dpi=300); plt.close(fig); log.info("多子图排版: %s",p); return p

def compose_all_figures(groups_results, output_dir, figures_dir=None, exp_type=None):
    sd=figures_dir or output_dir; log.info("开始生成图表...")
    for r in groups_results:
        if r["n"]>0: plot_single_group(r,output_dir,figures_dir=sd)
    plot_comparison(groups_results,output_dir,figures_dir=sd)
    nv=sum(1 for r in groups_results if r["n"]>0)
    if nv<=2: plot_multi_panel(groups_results,output_dir,layout=(1,nv),filename="multi_panel_stress_strain.png",figures_dir=sd)
    elif nv<=4: plot_multi_panel(groups_results,output_dir,layout=(2,2),filename="multi_panel_stress_strain.png",figures_dir=sd)
    if exp_type: log.info("  实验类型: %s", exp_type.label_cn)
    log.info("所有图表生成完成。")
