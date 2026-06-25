import SwiftUI

struct SparklineChart: View {
    let values: [Double]
    var color: Color = .blue

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            let minV = values.min() ?? 0
            let maxV = values.max() ?? 1
            let range = maxV - minV == 0 ? 1.0 : maxV - minV

            let points: [CGPoint] = values.enumerated().map { i, v in
                let x = values.count == 1 ? w / 2 : CGFloat(i) / CGFloat(values.count - 1) * w
                let y = h - CGFloat((v - minV) / range) * h
                return CGPoint(x: x, y: y)
            }

            if points.count > 1 {
                Path { p in
                    p.move(to: points[0])
                    for pt in points.dropFirst() { p.addLine(to: pt) }
                }
                .stroke(color, style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))

                Path { p in
                    p.move(to: CGPoint(x: points[0].x, y: h))
                    for pt in points { p.addLine(to: pt) }
                    p.addLine(to: CGPoint(x: points.last!.x, y: h))
                    p.closeSubpath()
                }
                .fill(LinearGradient(colors: [color.opacity(0.2), color.opacity(0.02)], startPoint: .top, endPoint: .bottom))

                ForEach(0..<points.count, id: \.self) { i in
                    if i == points.count - 1 {
                        Circle()
                            .fill(color)
                            .frame(width: 6, height: 6)
                            .position(points[i])
                    }
                }
            }
        }
    }
}
