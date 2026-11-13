#include <CoreGraphics/CoreGraphics.h>
#include <CoreFoundation/CoreFoundation.h>
#include <ImageIO/CGImageDestination.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int capture_rect(double x, double y, double w, double h, const char *out_path) {
    CGRect rect = CGRectMake(x, y, w, h);
    CGImageRef image = CGWindowListCreateImage(rect, kCGWindowListOptionOnScreenOnly, kCGNullWindowID, kCGWindowImageDefault);
    if (!image) {
        fprintf(stderr, "Failed to capture CGImage\n");
        return 1;
    }

    CFStringRef pathStr = CFStringCreateWithCString(NULL, out_path, kCFStringEncodingUTF8);
    CFURLRef url = CFURLCreateWithFileSystemPath(NULL, pathStr, kCFURLPOSIXPathStyle, false);
    CFRelease(pathStr);

    CFStringRef pngType = CFSTR("public.png");
    CGImageDestinationRef dest = CGImageDestinationCreateWithURL(url, pngType, 1, NULL);
    CFRelease(url);

    if (!dest) {
        CGImageRelease(image);
        fprintf(stderr, "Failed to create ImageDestination\n");
        return 1;
    }

    CGImageDestinationAddImage(dest, image, NULL);
    bool ok = CGImageDestinationFinalize(dest);
    CFRelease(dest);
    CGImageRelease(image);

    return ok ? 0 : 1;
}

int main(int argc, char *argv[]) {
    if (argc >= 6 && strcmp(argv[1], "--capture") == 0) {
        double x = atof(argv[2]);
        double y = atof(argv[3]);
        double w = atof(argv[4]);
        double h = atof(argv[5]);
        const char *path = argc > 6 ? argv[6] : "/tmp/hud_game_capture.png";
        return capture_rect(x, y, w, h, path);
    }

    CFArrayRef windowList = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID);
    if (!windowList) {
        printf("[]\n");
        return 0;
    }

    CFIndex count = CFArrayGetCount(windowList);
    printf("[\n");
    int first = 1;

    for (CFIndex i = 0; i < count; i++) {
        CFDictionaryRef dict = (CFDictionaryRef)CFArrayGetValueAtIndex(windowList, i);
        if (!dict) continue;

        CFStringRef ownerRef = (CFStringRef)CFDictionaryGetValue(dict, kCGWindowOwnerName);
        CFStringRef nameRef = (CFStringRef)CFDictionaryGetValue(dict, kCGWindowName);
        CFNumberRef layerRef = (CFNumberRef)CFDictionaryGetValue(dict, kCGWindowLayer);
        CFNumberRef idRef = (CFNumberRef)CFDictionaryGetValue(dict, kCGWindowNumber);
        CFDictionaryRef boundsRef = (CFDictionaryRef)CFDictionaryGetValue(dict, kCGWindowBounds);

        int layer = 0;
        if (layerRef) CFNumberGetValue(layerRef, kCFNumberIntType, &layer);
        if (layer != 0) continue;

        char owner[256] = {0};
        char name[256] = {0};
        if (ownerRef) CFStringGetCString(ownerRef, owner, sizeof(owner), kCFStringEncodingUTF8);
        if (nameRef) CFStringGetCString(nameRef, name, sizeof(name), kCFStringEncodingUTF8);

        if (strstr(owner, "WeChat") || strstr(owner, "微信")) {
            CGRect rect;
            if (boundsRef && CGRectMakeWithDictionaryRepresentation(boundsRef, &rect)) {
                int wid = 0;
                if (idRef) CFNumberGetValue(idRef, kCFNumberIntType, &wid);
                double aspect = rect.size.width > 0 ? (rect.size.height / rect.size.width) : 0;

                if (!first) printf(",\n");
                first = 0;
                printf("  {\"owner\": \"%s\", \"name\": \"%s\", \"id\": %d, \"x\": %.1f, \"y\": %.1f, \"width\": %.1f, \"height\": %.1f, \"aspectRatio\": %.3f}",
                       owner, name, wid, rect.origin.x, rect.origin.y, rect.size.width, rect.size.height, aspect);
            }
        }
    }

    printf("\n]\n");
    CFRelease(windowList);
    return 0;
}
