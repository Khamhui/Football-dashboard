import SwiftUI

// MARK: - Appear Animation Modifier

struct AppearAnimation: ViewModifier {
    let delay: Double
    @State private var appeared = false

    func body(content: Content) -> some View {
        content
            .opacity(appeared ? 1 : 0)
            .offset(y: appeared ? 0 : 12)
            .onAppear {
                withAnimation(.easeOut(duration: 0.4).delay(delay)) {
                    appeared = true
                }
            }
    }
}

extension View {
    func appearAnimation(delay: Double = 0) -> some View {
        modifier(AppearAnimation(delay: delay))
    }
}

// MARK: - Sparkline Draw Animation

struct SparklineDrawModifier: ViewModifier {
    @State private var trimEnd: CGFloat = 0

    func body(content: Content) -> some View {
        content
            .mask(
                GeometryReader { geo in
                    Rectangle()
                        .frame(width: geo.size.width * trimEnd)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            )
            .onAppear {
                withAnimation(.easeOut(duration: 0.8).delay(0.2)) {
                    trimEnd = 1
                }
            }
    }
}

extension View {
    func sparklineDrawAnimation() -> some View {
        modifier(SparklineDrawModifier())
    }
}

// MARK: - Boot Scan Line

struct BootScanLine: View {
    @State private var offset: CGFloat = 0
    @State private var opacity: Double = 1

    let color: Color
    var duration: Double = 0.6

    var body: some View {
        GeometryReader { geo in
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [.clear, color.opacity(0.4), color.opacity(0.8), color.opacity(0.4), .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                )
                .frame(height: 2)
                .offset(y: offset)
                .opacity(opacity)
                .onAppear {
                    withAnimation(.easeInOut(duration: duration)) {
                        offset = geo.size.height
                    }
                    withAnimation(.easeIn(duration: 0.3).delay(duration)) {
                        opacity = 0
                    }
                }
        }
        .allowsHitTesting(false)
    }
}

// MARK: - Pulse Animation

struct PulseModifier: ViewModifier {
    @State private var pulsing = false

    func body(content: Content) -> some View {
        content
            .scaleEffect(pulsing ? 1.0 : 0.95)
            .opacity(pulsing ? 1.0 : 0.7)
            .onAppear {
                withAnimation(.easeInOut(duration: 0.5).delay(0.3)) {
                    pulsing = true
                }
            }
    }
}

extension View {
    func pulseOnAppear() -> some View {
        modifier(PulseModifier())
    }
}
