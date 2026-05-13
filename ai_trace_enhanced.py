"""
增强 AI 痕迹检测 - 核心改进 4
从简单规则升级到统计分布对比
"""

import re
import math
from typing import List, Dict, Any, Tuple
from collections import Counter


class WritingStatistics:
    """文本写作风格统计特征"""
    def __init__(self, text: str):
        self.text = text
        self.lines = text.splitlines()
        self.sentences = self._split_sentences(text)
        self.words = self._split_words(text)

    def _split_sentences(self, text: str) -> List[str]:
        """按句末标点分句"""
        parts = re.split(r"[。！？!?]", text)
        return [p.strip() for p in parts if p.strip()]

    def _split_words(self, text: str) -> List[str]:
        """简单分词（按空白和标点）"""
        return re.findall(r"\w+", text)

    def sentence_length_stats(self) -> Dict[str, float]:
        """句子长度统计"""
        lengths = [len(s) for s in self.sentences if len(s) > 0]
        if not lengths:
            return {"mean": 0, "std": 0, "cv": 0}
        mean = sum(lengths) / len(lengths)
        variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
        std = math.sqrt(variance)
        cv = std / mean if mean > 0 else 0  # 变异系数
        return {"mean": mean, "std": std, "cv": cv}

    def paragraph_length_stats(self) -> Dict[str, float]:
        """段落长度统计"""
        paragraphs = [p for p in self.lines if p.strip()]
        lengths = [len(p) for p in paragraphs if len(p.strip()) > 0]
        if not lengths:
            return {"mean": 0, "std": 0, "cv": 0}
        mean = sum(lengths) / len(lengths)
        variance = sum((x - mean) ** 2 for x in lengths) / len(lengths)
        std = math.sqrt(variance)
        cv = std / mean if mean > 0 else 0
        return {"mean": mean, "std": std, "cv": cv}

    def dialogue_ratio(self) -> float:
        """对话比例（有引号的行数占比）"""
        if not self.lines:
            return 0
        dialogue_lines = [
            l for l in self.lines
            if ("“" in l and "”" in l) or ('"', l) or ('"', l)
        ]
        return len(dialogue_lines) / len(self.lines)

    def punctuation_patterns(self) -> Dict[str, float]:
        """标点模式统计"""
        if not self.text:
            return {}
        total = len(self.text)
        patterns = {
            "ellipsis": self.text.count("……") / (total / 100),  # 省略号频率
            "exclamation": self.text.count("！") / (total / 100),  # 感叹号频率
            "question": self.text.count("？") / (total / 100),  # 问号频率
        }
        return patterns

    def transition_word_count(self) -> int:
        """过渡词数量"""
        transitions = [
            "然而", "不过", "但是", "可是", "虽然", "尽管",
            "与此同时", "另一方面", "话虽如此", "值得注意的是",
            "然后", "接着", "随后", "之后", "接下来",
            "突然", "忽然", "猛地", "瞬间",
        ]
        count = 0
        for word in transitions:
            count += self.text.count(word)
        return count

    def emotional_expression_count(self) -> int:
        """情绪表达词汇数量（AI 常用的）"""
        emotion_patterns = [
            r"心中一[震惊凛痛酸暖]",
            r"不禁[一]?[笑叹怒哭喜]",
            r"他明白|她明白",
            r"这一刻",
            r"总之|显然",
        ]
        count = 0
        for pattern in emotion_patterns:
            count += len(list(re.finditer(pattern, self.text)))
        return count

    def all_stats(self) -> Dict[str, Any]:
        """所有统计特征"""
        return {
            "sentence_length": self.sentence_length_stats(),
            "paragraph_length": self.paragraph_length_stats(),
            "dialogue_ratio": self.dialogue_ratio(),
            "punctuation": self.punctuation_patterns(),
            "transition_count": self.transition_word_count(),
            "emotion_expr_count": self.emotional_expression_count(),
        }


class HumanWritingReference:
    """人类写作参考分布（简化版）"""
    @staticmethod
    def typical_sentence_cv() -> float:
        """人类写作典型的句子长度变异系数（通常 > 0.5）"""
        return 0.6

    @staticmethod
    def typical_paragraph_cv() -> float:
        """人类写作典型的段落长度变异系数（通常 > 0.7）"""
        return 0.8


def detect_ai_trace_statistical(text: str) -> Tuple[float, Dict[str, Any]]:
    """
    用统计方法检测 AI 痕迹，返回 (ai_score, details)
    ai_score 越高越可能是 AI 写的（0-100）
    """
    stats = WritingStatistics(text)
    details = {}
    score = 0

    # 1. 检查句子长度变异系数（AI 写的句子长度通常太均匀，CV < 0.4）
    sent_cv = stats.sentence_length_stats()["cv"]
    details["sentence_cv"] = sent_cv
    if sent_cv < 0.4:
        score += 25
    elif sent_cv < 0.5:
        score += 10

    # 2. 检查段落长度变异系数（AI 写的段落长度也容易太均匀）
    para_cv = stats.paragraph_length_stats()["cv"]
    details["paragraph_cv"] = para_cv
    if para_cv < 0.5:
        score += 20
    elif para_cv < 0.65:
        score += 8

    # 3. 检查过渡词密度
    trans_count = stats.transition_word_count()
    text_length = max(len(text), 100)
    trans_density = trans_count / (text_length / 1000)  # 每千字的过渡词
    details["transition_density"] = trans_density
    if trans_density > 3:
        score += 20
    elif trans_density > 2:
        score += 10

    # 4. 检查情绪表达词汇（AI 喜欢用固定的情绪表达）
    emotion_count = stats.emotional_expression_count()
    details["emotion_expr_count"] = emotion_count
    if emotion_count > 5:
        score += 15
    elif emotion_count > 2:
        score += 8

    # 5. 检查对话比例（AI 有时候要么全是对话要么全是叙述）
    dialogue_ratio = stats.dialogue_ratio()
    details["dialogue_ratio"] = dialogue_ratio
    if dialogue_ratio < 0.05 or dialogue_ratio > 0.6:
        score += 12

    # 归一化到 0-100
    ai_score = min(score, 100)
    return ai_score, details


def enhanced_ai_trace_analysis(text: str) -> Dict[str, Any]:
    """
    增强的 AI 痕迹分析
    """
    rule_score = 0
    rule_issues = []

    # 规则检测（保留原有能力）
    summary_patterns = [r"这一刻", r"总之", r"显然", r"不禁", r"他明白", r"她明白"]
    for pattern in summary_patterns:
        matches = list(re.finditer(pattern, text))
        if matches:
            rule_score += len(matches) * 3
            rule_issues.append({
                "pattern": pattern,
                "count": len(matches),
                "severity": "minor" if len(matches) <= 2 else "major",
            })

    # 过渡词检测
    transitions = ["然而", "不过", "与此同时", "另一方面", "话虽如此", "然后", "接着"]
    trans_count = sum(text.count(t) for t in transitions)
    if trans_count > 5:
        rule_score += (trans_count - 5) * 2
        rule_issues.append({
            "type": "transition_words",
            "count": trans_count,
            "severity": "minor" if trans_count <= 8 else "major",
        })

    # 统计检测（新能力）
    stat_score, stat_details = detect_ai_trace_statistical(text)

    # 综合得分
    combined_score = (rule_score * 0.4) + (stat_score * 0.6)
    combined_score = min(combined_score, 100)

    return {
        "combined_score": combined_score,
        "rule_score": rule_score,
        "statistical_score": stat_score,
        "rule_issues": rule_issues,
        "statistical_details": stat_details,
    }


def format_ai_trace_report(analysis_result: Dict[str, Any]) -> str:
    """格式化 AI 痕迹报告"""
    score = analysis_result["combined_score"]

    risk_level = "低" if score < 30 else "中" if score < 60 else "高"
    icon = "✅" if score < 30 else "⚠️" if score < 60 else "❌"

    lines = [
        f"# AI 痕迹检测报告",
        f"",
        f"{icon} 综合得分: {score:.1f} / 100（越高越像 AI）",
        f"风险等级: {risk_level}",
        f"",
    ]

    # 规则问题
    if analysis_result.get("rule_issues"):
        lines.append("## 规则检测发现的问题")
        for issue in analysis_result["rule_issues"][:5]:
            sev_icon = "⚠️" if issue["severity"] == "major" else "•"
            lines.append(f"{sev_icon} {issue}")
        if len(analysis_result["rule_issues"]) > 5:
            lines.append(f"... (还有 {len(analysis_result['rule_issues']) - 5} 个问题)")

    # 统计分析详情
    if "statistical_details" in analysis_result:
        details = analysis_result["statistical_details"]
        lines.extend([
            "",
            "## 统计分析详情",
        ])
        if "sentence_cv" in details:
            cv = details["sentence_cv"]
            status = "✅" if cv > 0.5 else "⚠️" if cv > 0.4 else "❌"
            lines.append(f"{status} 句子长度变异系数: {cv:.2f}（人类通常 > 0.5）")
        if "paragraph_cv" in details:
            cv = details["paragraph_cv"]
            status = "✅" if cv > 0.7 else "⚠️" if cv > 0.5 else "❌"
            lines.append(f"{status} 段落长度变异系数: {cv:.2f}（人类通常 > 0.7）")

    lines.extend([
        "",
        "建议：",
        "- 如果得分高，尝试用更自然的表达方式重写",
        "- 增加句子和段落长度的变化",
        "- 减少标准化的情绪表达（如「心中一震」、「他明白」）",
    ])

    return "\n".join(lines)
