#!/usr/bin/env python3
"""
Code Standards Compliance Analyzer for Trendbot Project
Checks code against defined coding standards including:
- File size limits (500 lines hard limit, 400 lines warning)
- Function size limits (40 lines)
- Class size limits (200 lines)
- Naming conventions
- Language usage (English requirement)
- Error handling patterns (no bare except)
- Documentation coverage
"""

import os
import ast
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Set
import json

@dataclass
class Violation:
    """Represents a code standards violation"""
    file_path: str
    rule: str
    severity: str  # CRITICAL, WARNING, INFO
    line_number: int
    description: str
    code_snippet: str = ""

@dataclass
class AnalysisReport:
    """Complete analysis report"""
    total_files: int = 0
    violations: List[Violation] = field(default_factory=list)
    file_stats: Dict = field(default_factory=dict)
    
    def add_violation(self, violation: Violation):
        """Adds a violation to the report."""
        self.violations.append(violation)
    
    def get_critical_count(self) -> int:
        """Returns the count of critical violations."""
        return len([v for v in self.violations if v.severity == "CRITICAL"])
    
    def get_warning_count(self) -> int:
        """Returns the count of warning violations."""
        return len([v for v in self.violations if v.severity == "WARNING"])

class CodeAnalyzer:
    """Analyzes Python code for standards compliance"""
    
    FORBIDDEN_NAMES = {'data', 'info', 'helper', 'temp', 'tmp'}
    VAGUE_PREFIXES = {'handle', 'process', 'do', 'manage'}
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.report = AnalysisReport()
    
    def analyze_project(self) -> AnalysisReport:
        """Analyze entire project"""
        python_files = list(self.project_root.rglob("*.py"))
        # Exclude virtual environment and cache directories
        python_files = [
            f for f in python_files 
            if not any(part in f.parts for part in ['.venv', '__pycache__', '.pytest_cache', '.git'])
        ]
        
        self.report.total_files = len(python_files)
        
        for py_file in python_files:
            self.analyze_file(py_file)
        
        return self.report
    
    def analyze_file(self, file_path: Path):
        """Analyze a single Python file"""
        rel_path = str(file_path.relative_to(self.project_root))
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.splitlines()
            
            # File size check
            line_count = len(lines)
            self.report.file_stats[rel_path] = {'lines': line_count}
            
            if line_count > 500:
                self.report.add_violation(Violation(
                    file_path=rel_path,
                    rule="FILE_SIZE_LIMIT",
                    severity="CRITICAL",
                    line_number=1,
                    description=f"File has {line_count} lines (HARD LIMIT: 500 lines)"
                ))
            elif line_count > 400:
                self.report.add_violation(Violation(
                    file_path=rel_path,
                    rule="FILE_SIZE_WARNING",
                    severity="WARNING",
                    line_number=1,
                    description=f"File has {line_count} lines (WARNING: approaching 500 line limit)"
                ))
            
            # Parse AST for deeper analysis
            try:
                tree = ast.parse(content, filename=str(file_path))
                self.analyze_ast(tree, rel_path, lines)
            except SyntaxError as e:
                self.report.add_violation(Violation(
                    file_path=rel_path,
                    rule="SYNTAX_ERROR",
                    severity="CRITICAL",
                    line_number=e.lineno or 1,
                    description=f"Syntax error: {e.msg}"
                ))
            
            # Check for non-English comments
            self.check_language(lines, rel_path)
            
            # Check for bare except
            self.check_bare_except(content, lines, rel_path)
            
            # Check for hardcoded secrets (basic patterns)
            self.check_hardcoded_secrets(content, lines, rel_path)
            
        except Exception as e:
            self.report.add_violation(Violation(
                file_path=rel_path,
                rule="FILE_READ_ERROR",
                severity="WARNING",
                line_number=1,
                description=f"Could not analyze file: {str(e)}"
            ))
    
    def analyze_ast(self, tree: ast.AST, file_path: str, lines: List[str]):
        """Analyze AST for functions and classes"""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self.check_function(node, file_path, lines)
            elif isinstance(node, ast.ClassDef):
                self.check_class(node, file_path, lines)
            elif isinstance(node, (ast.Name, ast.arg)):
                self.check_naming(node, file_path)
    
    def check_function(self, node: ast.FunctionDef, file_path: str, lines: List[str]):
        """Check function compliance"""
        func_name = node.name
        start_line = node.lineno
        end_line = node.end_lineno or start_line
        func_length = end_line - start_line + 1
        
        # Function size check
        if func_length > 40:
            self.report.add_violation(Violation(
                file_path=file_path,
                rule="FUNCTION_SIZE_LIMIT",
                severity="CRITICAL",
                line_number=start_line,
                description=f"Function '{func_name}' has {func_length} lines (LIMIT: 40 lines)",
                code_snippet=f"def {func_name}(...) # lines {start_line}-{end_line}"
            ))
        
        # Check if function has docstring (for public functions)
        if not func_name.startswith('_') and not ast.get_docstring(node):
            self.report.add_violation(Violation(
                file_path=file_path,
                rule="MISSING_DOCSTRING",
                severity="WARNING",
                line_number=start_line,
                description=f"Public function '{func_name}' missing docstring"
            ))
        
        # Check naming convention
        if func_name in self.FORBIDDEN_NAMES:
            self.report.add_violation(Violation(
                file_path=file_path,
                rule="FORBIDDEN_NAME",
                severity="CRITICAL",
                line_number=start_line,
                description=f"Function uses forbidden vague name: '{func_name}'"
            ))
    
    def check_class(self, node: ast.ClassDef, file_path: str, lines: List[str]):
        """Check class compliance"""
        class_name = node.name
        start_line = node.lineno
        end_line = node.end_lineno or start_line
        class_length = end_line - start_line + 1
        
        # Class size check
        if class_length > 200:
            self.report.add_violation(Violation(
                file_path=file_path,
                rule="CLASS_SIZE_LIMIT",
                severity="WARNING",
                line_number=start_line,
                description=f"Class '{class_name}' has {class_length} lines (LIMIT: 200 lines)",
                code_snippet=f"class {class_name}: # lines {start_line}-{end_line}"
            ))
        
        # Check if class has docstring
        if not ast.get_docstring(node):
            self.report.add_violation(Violation(
                file_path=file_path,
                rule="MISSING_DOCSTRING",
                severity="WARNING",
                line_number=start_line,
                description=f"Class '{class_name}' missing docstring"
            ))
    
    def check_naming(self, node, file_path: str):
        """Check naming conventions"""
        name = None
        line_no = 1
        
        if isinstance(node, ast.Name):
            name = node.id
            line_no = node.lineno
        elif isinstance(node, ast.arg):
            name = node.arg
            line_no = node.lineno
        
        if name and name in self.FORBIDDEN_NAMES:
            self.report.add_violation(Violation(
                file_path=file_path,
                rule="FORBIDDEN_NAME",
                severity="CRITICAL",
                line_number=line_no,
                description=f"Variable uses forbidden vague name: '{name}'"
            ))
    
    def check_language(self, lines: List[str], file_path: str):
        """Check for non-English comments and docstrings"""
        # Simple heuristic: check for Turkish characters
        turkish_pattern = re.compile(r'[ğüşöçİĞÜŞÖÇ]')
        
        for i, line in enumerate(lines, 1):
            # Check comments
            if '#' in line:
                comment = line[line.index('#'):]
                if turkish_pattern.search(comment):
                    self.report.add_violation(Violation(
                        file_path=file_path,
                        rule="NON_ENGLISH_COMMENT",
                        severity="WARNING",
                        line_number=i,
                        description="Comment contains non-English characters (Turkish)",
                        code_snippet=line.strip()[:60]
                    ))
            
            # Check docstrings
            if '"""' in line or "'''" in line:
                if turkish_pattern.search(line):
                    self.report.add_violation(Violation(
                        file_path=file_path,
                        rule="NON_ENGLISH_DOCSTRING",
                        severity="WARNING",
                        line_number=i,
                        description="Docstring contains non-English characters (Turkish)",
                        code_snippet=line.strip()[:60]
                    ))
    
    def check_bare_except(self, content: str, lines: List[str], file_path: str):
        """Check for bare except: clauses"""
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == 'except:' or stripped.startswith('except:'):
                self.report.add_violation(Violation(
                    file_path=file_path,
                    rule="BARE_EXCEPT",
                    severity="CRITICAL",
                    line_number=i,
                    description="Bare 'except:' block found (must specify exception type)",
                    code_snippet=line.strip()
                ))
    
    def check_hardcoded_secrets(self, content: str, lines: List[str], file_path: str):
        """Check for potential hardcoded secrets"""
        # Skip .env files
        if file_path.endswith('.env'):
            return
        
        secret_patterns = [
            (r'password\s*=\s*["\'](?!.*\{.*\})[^"\']{3,}["\']', 'hardcoded password'),
            (r'api[_-]?key\s*=\s*["\'](?!.*\{.*\})[^"\']{10,}["\']', 'hardcoded API key'),
            (r'secret\s*=\s*["\'](?!.*\{.*\})[^"\']{10,}["\']', 'hardcoded secret'),
            (r'token\s*=\s*["\'](?!.*\{.*\})[^"\']{10,}["\']', 'hardcoded token'),
        ]
        
        for pattern, desc in secret_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                line_num = content[:match.start()].count('\n') + 1
                self.report.add_violation(Violation(
                    file_path=file_path,
                    rule="HARDCODED_SECRET",
                    severity="CRITICAL",
                    line_number=line_num,
                    description=f"Potential {desc} detected",
                    code_snippet=lines[line_num - 1].strip()[:60]
                ))
    
    def generate_report(self) -> str:
        """Generate human-readable report"""
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("CODE STANDARDS COMPLIANCE REPORT - TRENDBOT PROJECT")
        report_lines.append("=" * 80)
        report_lines.append(f"\nTotal files analyzed: {self.report.total_files}")
        report_lines.append(f"Total violations: {len(self.report.violations)}")
        report_lines.append(f"  - CRITICAL: {self.report.get_critical_count()}")
        report_lines.append(f"  - WARNING: {self.report.get_warning_count()}")
        report_lines.append("\n" + "=" * 80)
        
        # Group violations by rule
        violations_by_rule = {}
        for v in self.report.violations:
            if v.rule not in violations_by_rule:
                violations_by_rule[v.rule] = []
            violations_by_rule[v.rule].append(v)
        
        # Sort rules by severity and count
        sorted_rules = sorted(
            violations_by_rule.items(),
            key=lambda x: (
                -len([v for v in x[1] if v.severity == "CRITICAL"]),
                -len(x[1])
            )
        )
        
        for rule, violations in sorted_rules:
            critical_count = len([v for v in violations if v.severity == "CRITICAL"])
            warning_count = len([v for v in violations if v.severity == "WARNING"])
            
            report_lines.append(f"\n{'─' * 80}")
            report_lines.append(f"RULE: {rule}")
            report_lines.append(f"Count: {len(violations)} (Critical: {critical_count}, Warning: {warning_count})")
            report_lines.append('─' * 80)
            
            # Group by file
            files_with_violations = {}
            for v in violations:
                if v.file_path not in files_with_violations:
                    files_with_violations[v.file_path] = []
                files_with_violations[v.file_path].append(v)
            
            for file_path, file_violations in sorted(files_with_violations.items()):
                report_lines.append(f"\n📁 {file_path}")
                for v in sorted(file_violations, key=lambda x: x.line_number):
                    severity_icon = "🔴" if v.severity == "CRITICAL" else "🟡"
                    report_lines.append(f"  {severity_icon} Line {v.line_number}: {v.description}")
                    if v.code_snippet:
                        report_lines.append(f"     └─ {v.code_snippet}")
        
        report_lines.append("\n" + "=" * 80)
        report_lines.append("TOP 10 LARGEST FILES")
        report_lines.append("=" * 80)
        
        sorted_files = sorted(
            self.report.file_stats.items(),
            key=lambda x: x[1]['lines'],
            reverse=True
        )[:10]
        
        for file_path, stats in sorted_files:
            status = ""
            if stats['lines'] > 500:
                status = " ❌ EXCEEDS LIMIT"
            elif stats['lines'] > 400:
                status = " ⚠️  WARNING"
            report_lines.append(f"{stats['lines']:4d} lines - {file_path}{status}")
        
        return "\n".join(report_lines)

def main():
    """Main entry point"""
    project_root = "/home/fury/projects/trendbot"
    
    print("Starting code standards compliance analysis...")
    print(f"Project root: {project_root}\n")
    
    analyzer = CodeAnalyzer(project_root)
    report = analyzer.analyze_project()
    
    # Generate and save report
    report_text = analyzer.generate_report()
    
    # Save to file
    report_path = Path(project_root) / "reports" / "code_standards_compliance.txt"
    report_path.parent.mkdir(exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    
    print(report_text)
    print(f"\n\nReport saved to: {report_path}")
    
    # Also save as JSON for programmatic access
    json_path = report_path.with_suffix('.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_files': report.total_files,
            'total_violations': len(report.violations),
            'critical_count': report.get_critical_count(),
            'warning_count': report.get_warning_count(),
            'violations': [
                {
                    'file': v.file_path,
                    'rule': v.rule,
                    'severity': v.severity,
                    'line': v.line_number,
                    'description': v.description,
                    'snippet': v.code_snippet
                }
                for v in report.violations
            ],
            'file_stats': report.file_stats
        }, f, indent=2)
    
    print(f"JSON report saved to: {json_path}")

if __name__ == "__main__":
    main()
