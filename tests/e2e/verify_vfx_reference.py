from __future__ import annotations

import argparse
import base64
from io import BytesIO
import json
import math
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps


def load_reference(path: Path) -> Image.Image:
    if path.suffix == ".b64":
        raw = base64.b64decode(path.read_text(encoding="ascii"), validate=True)
        image = Image.open(BytesIO(raw)); image.load(); return image.convert("RGBA")
    image = Image.open(path); image.load(); return image.convert("RGBA")


def split_sheet(image: Image.Image, columns: int = 4, rows: int = 2) -> list[Image.Image]:
    width, height = image.size
    if width % columns or height % rows:
        raise AssertionError(f"sheet {image.size} is not divisible by {columns}x{rows}")
    cw, ch = width // columns, height // rows
    return [image.crop((c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)).convert("RGBA") for r in range(rows) for c in range(columns)]


def color_fractions(frame: Image.Image) -> dict[str, float]:
    pixels = [pixel for pixel in frame.getdata() if pixel[3] > 16]
    if not pixels: return {"white": 0.0, "cyan": 0.0, "blue": 0.0}
    n = len(pixels)
    return {
        "white": sum(1 for r,g,b,_ in pixels if r > 210 and g > 225 and b > 225) / n,
        "cyan": sum(1 for r,g,b,_ in pixels if g > 125 and b > 160 and b >= r * 1.15) / n,
        "blue": sum(1 for r,g,b,_ in pixels if b > 105 and b >= r * 1.30) / n,
    }


def alpha_area(frame: Image.Image, threshold: int = 16) -> int:
    return sum(1 for value in frame.getchannel("A").getdata() if value > threshold)


def normalized_mask(frame: Image.Image, size: int = 96, threshold: int = 32) -> Image.Image:
    alpha = frame.getchannel("A").point(lambda v: 255 if v > threshold else 0)
    bbox = alpha.getbbox()
    if bbox is None: return Image.new("1", (size, size), 0)
    crop = alpha.crop(bbox); target = size - 12
    scale = min(target / crop.width, target / crop.height)
    resized = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.Resampling.NEAREST)
    canvas = Image.new("L", (size, size), 0); canvas.paste(resized, ((size-resized.width)//2, (size-resized.height)//2))
    return canvas.point(lambda v: 255 if v else 0).convert("1")


def mask_iou(left: Image.Image, right: Image.Image) -> float:
    a, b = list(left.getdata()), list(right.getdata())
    inter = sum(1 for x,y in zip(a,b) if x and y); union = sum(1 for x,y in zip(a,b) if x or y)
    return inter / union if union else 1.0


def roughness(frame: Image.Image) -> float:
    mask = normalized_mask(frame, 96, threshold=96); data = list(mask.getdata()); w,h = mask.size
    area = sum(1 for v in data if v)
    if not area: return 0.0
    boundary = 0
    for y in range(1,h-1):
        for x in range(1,w-1):
            i = y*w+x
            if data[i] and not (data[i-1] and data[i+1] and data[i-w] and data[i+w]): boundary += 1
    return boundary / math.sqrt(area)


def glow_fraction(frame: Image.Image) -> float:
    alpha = list(frame.getchannel("A").getdata()); active = sum(1 for v in alpha if v > 8)
    return (sum(1 for v in alpha if 8 < v < 96) / active) if active else 0.0


def bright_outside_fraction(frame: Image.Image) -> float:
    """Measure white/cyan lightning that visibly escapes the saturated slash body.

    The old alpha-only body mask accidentally classified branch pixels and their
    glow as body, then a 15 px dilation swallowed the very lightning this metric
    was supposed to measure. Use chroma to identify blue/cyan body pixels and a
    small 5 px guard band around them instead.
    """
    rgba = frame.convert("RGBA"); pixels = list(rgba.getdata())
    body = Image.new("L", rgba.size, 0)
    body.putdata([
        255 if a > 80 and b > 120 and b >= r * 1.25 and not (r > 175 and g > 190 and b > 200) else 0
        for r,g,b,a in pixels
    ])
    body = body.filter(ImageFilter.MaxFilter(5)); body_data = list(body.getdata())
    active = sum(1 for *_,a in pixels if a > 16)
    if not active: return 0.0
    count = sum(
        1 for i,(r,g,b,a) in enumerate(pixels)
        if a > 32 and not body_data[i] and b > 175 and g > 165 and (r > 150 or g > 205)
    )
    return count / active


def frame_metrics(frames: list[Image.Image]) -> list[dict[str, float | int]]:
    result=[]
    for frame in frames:
        c=color_fractions(frame)
        result.append({"area":alpha_area(frame),"white":c["white"],"cyan":c["cyan"],"blue":c["blue"],"roughness":roughness(frame),"glowFraction":glow_fraction(frame),"brightOutsideFraction":bright_outside_fraction(frame)})
    return result


def write_overlay(reference: Image.Image, output: Image.Image, path: Path) -> None:
    width=max(reference.width, output.width)
    ref=ImageOps.contain(reference,(width,max(1,round(reference.height*width/reference.width))))
    out=ImageOps.contain(output,(width,max(1,round(output.height*width/output.width))))
    canvas=Image.new("RGBA",(width,ref.height+out.height),(0,0,0,0)); canvas.paste(ref,((width-ref.width)//2,0),ref); canvas.paste(out,((width-out.width)//2,ref.height),out)
    path.parent.mkdir(parents=True,exist_ok=True); canvas.save(path)


def verify(reference_path: Path, output_root: Path, qa_root: Path) -> None:
    reference_sheet=load_reference(reference_path); output_sheet=Image.open(output_root/"vfx_sheet.png").convert("RGBA")
    refs, outs=split_sheet(reference_sheet), split_sheet(output_sheet)
    ref_metrics,out_metrics=frame_metrics(refs),frame_metrics(outs)
    ref_areas=[int(x["area"]) for x in ref_metrics]; out_areas=[int(x["area"]) for x in out_metrics]
    ref_peak=max(range(len(ref_areas)),key=ref_areas.__getitem__); out_peak=max(range(len(out_areas)),key=out_areas.__getitem__)
    ious=[mask_iou(normalized_mask(r),normalized_mask(o)) for r,o in zip(refs,outs)]; peak_iou=ious[out_peak]; mean_iou=sum(ious)/len(ious)
    failures=[]
    if abs(ref_peak-out_peak)>1: failures.append(f"peak timing differs too much: reference={ref_peak+1}, output={out_peak+1}")
    if out_areas[out_peak] <= out_areas[0]*1.65: failures.append("output lacks reference-like buildup")
    if out_areas[-1] >= out_areas[out_peak]*0.58: failures.append("output lacks reference-like breakup/decay")
    peak, ref_peak_m = out_metrics[out_peak], ref_metrics[ref_peak]
    if float(peak["white"]) < 0.025: failures.append("peak frame lacks a white-hot core")
    if float(peak["white"]) > max(0.30,float(ref_peak_m["white"])+0.14): failures.append("peak frame is too white/wash-out relative to golden")
    if float(peak["cyan"]) < 0.10: failures.append("peak frame lacks a cyan inner-energy layer")
    if float(peak["cyan"]) > min(0.80,float(ref_peak_m["cyan"])+0.36): failures.append("peak frame has too much cyan coverage relative to golden")
    if float(peak["blue"]) < max(0.45,float(ref_peak_m["blue"])*0.68): failures.append("peak frame lacks a dominant deep-blue body")
    if peak_iou < 0.16 or mean_iou < 0.12: failures.append(f"crescent silhouette is too far from golden direction: peak IoU={peak_iou:.3f}, mean IoU={mean_iou:.3f}")
    if float(peak["roughness"]) < float(ref_peak_m["roughness"])*0.55: failures.append("peak silhouette is still too smooth/vector-like relative to golden")
    if float(out_metrics[-1]["roughness"]) <= float(peak["roughness"])*1.02: failures.append("decay frame is not visibly more fragmented than the peak")
    if float(peak["glowFraction"]) < 0.03: failures.append("peak frame lacks a soft external glow falloff")
    if float(peak["brightOutsideFraction"]) < 0.001: failures.append("peak frame lacks visible bright lightning outside the main body")
    report={"reference":str(reference_path),"output":str(output_root/"vfx_sheet.png"),"referencePeakFrame":ref_peak+1,"outputPeakFrame":out_peak+1,"frameIoU":[round(v,4) for v in ious],"meanIoU":round(mean_iou,4),"peakIoU":round(peak_iou,4),"referenceMetrics":ref_metrics,"outputMetrics":out_metrics,"failures":failures}
    qa_root.mkdir(parents=True,exist_ok=True); (qa_root/"comparison_report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    write_overlay(reference_sheet,output_sheet,qa_root/"comparison_overlay.png"); write_overlay(reference_sheet,output_sheet,qa_root/"golden_vs_output.png")
    if failures: raise AssertionError("VFX golden-reference QA failed:\n- "+"\n- ".join(failures))
    print(f"VFX golden-reference QA verified: peak IoU={peak_iou:.3f}, mean IoU={mean_iou:.3f}")


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--reference",required=True); parser.add_argument("--output",required=True); parser.add_argument("--qa-output",required=True); args=parser.parse_args()
    verify(Path(args.reference),Path(args.output),Path(args.qa_output))


if __name__=="__main__": main()
