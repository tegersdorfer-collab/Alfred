import Foundation

struct WikiLink {
    let title: String
    let range: Range<String.Index>
}

enum WikiLinkParser {
    static func extractLinks(from text: String) -> [String] {
        let pattern = #"\[\[([^\[\]]+)\]\]"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let ns = text as NSString
        return regex.matches(in: text, range: NSRange(text.startIndex..., in: text))
            .compactMap { match -> String? in
                guard match.numberOfRanges > 1 else { return nil }
                let range = match.range(at: 1)
                guard range.location != NSNotFound else { return nil }
                return ns.substring(with: range)
            }
    }

    /// Renders [[title]] as styled inline text for display
    static func renderMarkdown(_ text: String) -> AttributedString {
        var result = (try? AttributedString(markdown: text)) ?? AttributedString(text)
        // Highlight [[links]]
        let pattern = #"\[\[([^\[\]]+)\]\]"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return result }
        let plain = text
        let ns = plain as NSString
        let matches = regex.matches(in: plain, range: NSRange(plain.startIndex..., in: plain))
        for match in matches.reversed() {
            guard let range = Range(match.range, in: plain) else { continue }
            let linkText = String(plain[range]).dropFirst(2).dropLast(2)
            if let attrRange = result.range(of: String(plain[range])) {
                result[attrRange].foregroundColor = .purple
                result[attrRange].underlineStyle = .single
            }
            _ = linkText
        }
        return result
    }
}
