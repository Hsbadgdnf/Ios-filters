import Foundation
import CoreImage
import CoreGraphics

let size = 33
let width = size * size // 1089
let height = size       // 33
let totalPixels = width * height

// 1. Build an exact 33x33x33 Identity Color Lattice in memory (RGBA8)
var rawIn = [UInt8](repeating: 255, count: totalPixels * 4)

for b in 0..<size {
    for g in 0..<size {
        for r in 0..<size {
            let index = b * (size * size) + g * size + r
            let offset = index * 4
            rawIn[offset + 0] = UInt8(round(Double(r) / Double(size - 1) * 255.0))
            rawIn[offset + 1] = UInt8(round(Double(g) / Double(size - 1) * 255.0))
            rawIn[offset + 2] = UInt8(round(Double(b) / Double(size - 1) * 255.0))
            rawIn[offset + 3] = 255
        }
    }
}

let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
let context = CIContext(options: [
    .workingColorSpace: colorSpace,
    .outputColorSpace: colorSpace,
    .useSoftwareRenderer: false
])

let bitmapInfo = CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue)
let provider = CGDataProvider(data: Data(rawIn) as CFData)!
let cgImageIn = CGImage(
    width: width,
    height: height,
    bitsPerComponent: 8,
    bitsPerPixel: 32,
    bytesPerRow: width * 4,
    space: colorSpace,
    bitmapInfo: bitmapInfo,
    provider: provider,
    decode: nil,
    shouldInterpolate: false,
    intent: .defaultIntent
)!

let inputCIImage = CIImage(cgImage: cgImageIn)

// 2. Map Display Names to Apple's internal CoreImage Filter Names (with fallbacks)
let filterTargets: [(displayName: String, ciNames: [String])] = [
    // Modern iOS Photos App Filters (9)
    ("iOS_Vivid",          ["CIPhotoEffect3DVivid", "CIPhotoEffectVivid"]),
    ("iOS_Vivid_Warm",     ["CIPhotoEffect3DVividWarm", "CIPhotoEffectVividWarm"]),
    ("iOS_Vivid_Cool",     ["CIPhotoEffect3DVividCool", "CIPhotoEffectVividCool"]),
    ("iOS_Dramatic",       ["CIPhotoEffect3DDramatic", "CIPhotoEffectDramatic"]),
    ("iOS_Dramatic_Warm",  ["CIPhotoEffect3DDramaticWarm", "CIPhotoEffectDramaticWarm"]),
    ("iOS_Dramatic_Cool",  ["CIPhotoEffect3DDramaticCool", "CIPhotoEffectDramaticCool"]),
    ("iOS_Mono",           ["CIPhotoEffectMono"]),
    ("iOS_Silvertone",     ["CIPhotoEffect3DSilverplate", "CIPhotoEffectSilvertone", "CIPhotoEffectTonal"]),
    ("iOS_Noir",           ["CIPhotoEffect3DNoir", "CIPhotoEffectNoir"]),
    // Classic iOS Built-in Filters (Bonus)
    ("iOS_Chrome",         ["CIPhotoEffectChrome"]),
    ("iOS_Fade",           ["CIPhotoEffectFade"]),
    ("iOS_Instant",        ["CIPhotoEffectInstant"]),
    ("iOS_Process",        ["CIPhotoEffectProcess"]),
    ("iOS_Transfer",       ["CIPhotoEffectTransfer"]),
    ("iOS_Tonal",          ["CIPhotoEffectTonal"])
]

let outDir = URL(fileURLWithPath: "output_cubes")
try? FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

for target in filterTargets {
    var activeFilter: CIFilter? = nil
    var usedName = ""
    
    for candidate in target.ciNames {
        if let f = CIFilter(name: candidate) {
            activeFilter = f
            usedName = candidate
            break
        }
    }
    
    guard let filter = activeFilter else {
        print("Skipping \(target.displayName) - filter not found in macOS runtime")
        continue
    }
    
    filter.setDefaults()
    filter.setValue(inputCIImage, forKey: kCIInputImageKey)
    
    guard let outputCIImage = filter.outputImage else { continue }
    
    var rawOut = [UInt8](repeating: 0, count: totalPixels * 4)
    context.render(
        outputCIImage,
        toBitmap: &rawOut,
        rowBytes: width * 4,
        bounds: CGRect(x: 0, y: 0, width: width, height: height),
        format: .RGBA8,
        colorSpace: colorSpace
    )
    
    var cubeText = "TITLE \"\(target.displayName)\"\n"
    cubeText += "# Extracted from Apple CoreImage (\(usedName))\n"
    cubeText += "LUT_3D_SIZE \(size)\n"
    cubeText += "DOMAIN_MIN 0.0 0.0 0.0\n"
    cubeText += "DOMAIN_MAX 1.0 1.0 1.0\n"
    
    for i in 0..<totalPixels {
        let offset = i * 4
        let rf = Double(rawOut[offset + 0]) / 255.0
        let gf = Double(rawOut[offset + 1]) / 255.0
        let bf = Double(rawOut[offset + 2]) / 255.0
        cubeText += String(format: "%.6f %.6f %.6f\n", rf, gf, bf)
    }
    
    let fileURL = outDir.appendingPathComponent("\(target.displayName).cube")
    try! cubeText.write(to: fileURL, atomically: true, encoding: .utf8)
    print("Extracted \(target.displayName).cube via \(usedName)")
}
