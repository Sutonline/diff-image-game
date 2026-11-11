# Image Difference Game Domain

A local verification and comparison engine designed to automatically detect and highlight visual differences in "spot the difference" puzzle game images without relying on large vision-language models.

## Language

**Game Sheet**:
A single composite image containing two aligned panels of a scene (arranged side-by-side or stacked top-and-bottom) with subtle visual differences.
_Avoid_: Screenshot, raw image, canvas.

**Reference Panel**:
The primary, baseline sub-image (typically the left or top panel) used as the ground truth.
_Avoid_: Original, master, left image.

**Target Panel**:
The modified sub-image (typically the right or bottom panel) containing the variations to be identified.
_Avoid_: Comparison image, changed image, right image.

**Seam**:
The boundary, dividing line, or separation margin between the Reference Panel and the Target Panel.
_Avoid_: Split line, middle gap.

**Difference Area**:
A contiguous clustered region of pixels that exceeds the discrepancy threshold between the Reference Panel and Target Panel.
_Avoid_: Discrepancy spot, anomaly, defect.

**Difference Mark**:
A visual red circle or bounding outline drawn over detected Difference Areas on the output image.
_Avoid_: Red circle, annotation, box.
