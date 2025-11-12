#!/usr/bin/env python3
"""
Korean Content Validation Script

Automated script to scan generated content for English text and validate
Korean content quality in VDOS simulation outputs.
"""

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from virtualoffice.common.korean_validation import KoreanContentValidator
from virtualoffice.common.localization import LocalizationManager


class KoreanContentScanner:
    """Scanner for Korean content validation in VDOS outputs"""
    
    def __init__(self, db_path: str = None, strict_mode: bool = True):
        """
        Initialize Korean content scanner.
        
        Args:
            db_path: Path to VDOS database file
            strict_mode: Whether to use strict validation rules
        """
        self.db_path = db_path or self._find_db_path()
        self.validator = KoreanContentValidator(strict_mode=strict_mode)
        self.localization_manager = LocalizationManager("ko")
        self.violations = []
        
    def _find_db_path(self) -> str:
        """Find VDOS database path"""
        possible_paths = [
            "src/virtualoffice/vdos.db",
            "vdos.db",
            os.getenv("VDOS_DB_PATH", "")
        ]
        
        for path in possible_paths:
            if path and os.path.exists(path):
                return path
        
        raise FileNotFoundError("Could not find VDOS database file")
    
    def scan_database_content(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scan all content in VDOS database for Korean validation issues.
        
        Returns:
            Dictionary of violations by content type
        """
        violations = {
            "emails": [],
            "chat_messages": [],
            "hourly_plans": [],
            "daily_reports": [],
            "simulation_reports": [],
            "personas": []
        }
        
        if not os.path.exists(self.db_path):
            print(f"Database not found: {self.db_path}")
            return violations
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            # Scan emails
            violations["emails"] = self._scan_emails(conn)
            
            # Scan chat messages
            violations["chat_messages"] = self._scan_chat_messages(conn)
            
            # Scan hourly plans
            violations["hourly_plans"] = self._scan_hourly_plans(conn)
            
            # Scan daily reports
            violations["daily_reports"] = self._scan_daily_reports(conn)
            
            # Scan simulation reports
            violations["simulation_reports"] = self._scan_simulation_reports(conn)
            
            # Scan personas
            violations["personas"] = self._scan_personas(conn)
            
        finally:
            conn.close()
        
        return violations
    
    def _scan_emails(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """Scan email content for Korean validation issues"""
        violations = []
        
        cursor = conn.execute("""
            SELECT id, sender, subject, body, created_at 
            FROM emails 
            ORDER BY created_at DESC
        """)
        
        for row in cursor:
            # Check subject
            if row["subject"]:
                is_valid, issues = self.validator.validate_korean_content(row["subject"])
                if not is_valid:
                    violations.append({
                        "type": "email_subject",
                        "id": row["id"],
                        "sender": row["sender"],
                        "content": row["subject"][:100],
                        "issues": issues,
                        "created_at": row["created_at"]
                    })
            
            # Check body
            if row["body"]:
                is_valid, issues = self.validator.validate_korean_content(row["body"])
                if not is_valid:
                    violations.append({
                        "type": "email_body",
                        "id": row["id"],
                        "sender": row["sender"],
                        "content": row["body"][:200],
                        "issues": issues,
                        "created_at": row["created_at"]
                    })
        
        return violations
    
    def _scan_chat_messages(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """Scan chat message content for Korean validation issues"""
        violations = []
        
        cursor = conn.execute("""
            SELECT id, sender, body, room_id, created_at 
            FROM chat_messages 
            ORDER BY created_at DESC
        """)
        
        for row in cursor:
            if row["body"]:
                is_valid, issues = self.validator.validate_korean_content(row["body"])
                if not is_valid:
                    violations.append({
                        "type": "chat_message",
                        "id": row["id"],
                        "sender": row["sender"],
                        "room_id": row["room_id"],
                        "content": row["body"][:200],
                        "issues": issues,
                        "created_at": row["created_at"]
                    })
        
        return violations
    
    def _scan_hourly_plans(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """Scan hourly plan content for Korean validation issues"""
        violations = []
        
        cursor = conn.execute("""
            SELECT id, person_id, content, tick, created_at 
            FROM hourly_plans 
            ORDER BY created_at DESC
        """)
        
        for row in cursor:
            if row["content"]:
                is_valid, issues = self.validator.validate_korean_content(row["content"])
                if not is_valid:
                    violations.append({
                        "type": "hourly_plan",
                        "id": row["id"],
                        "person_id": row["person_id"],
                        "tick": row["tick"],
                        "content": row["content"][:300],
                        "issues": issues,
                        "created_at": row["created_at"]
                    })
                
                # Check for specific localization issues
                content = row["content"]
                if "Scheduled Communications" in content:
                    violations.append({
                        "type": "hourly_plan_localization",
                        "id": row["id"],
                        "person_id": row["person_id"],
                        "tick": row["tick"],
                        "content": content[:300],
                        "issues": ["Contains English 'Scheduled Communications' instead of Korean '예정된 커뮤니케이션'"],
                        "created_at": row["created_at"]
                    })
        
        return violations
    
    def _scan_daily_reports(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """Scan daily report content for Korean validation issues"""
        violations = []
        
        cursor = conn.execute("""
            SELECT id, person_id, content, day_index, created_at 
            FROM daily_reports 
            ORDER BY created_at DESC
        """)
        
        for row in cursor:
            if row["content"]:
                is_valid, issues = self.validator.validate_korean_content(row["content"])
                if not is_valid:
                    violations.append({
                        "type": "daily_report",
                        "id": row["id"],
                        "person_id": row["person_id"],
                        "day_index": row["day_index"],
                        "content": row["content"][:300],
                        "issues": issues,
                        "created_at": row["created_at"]
                    })
        
        return violations
    
    def _scan_simulation_reports(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """Scan simulation report content for Korean validation issues"""
        violations = []
        
        cursor = conn.execute("""
            SELECT id, content, total_ticks, created_at 
            FROM simulation_reports 
            ORDER BY created_at DESC
        """)
        
        for row in cursor:
            if row["content"]:
                is_valid, issues = self.validator.validate_korean_content(row["content"])
                if not is_valid:
                    violations.append({
                        "type": "simulation_report",
                        "id": row["id"],
                        "total_ticks": row["total_ticks"],
                        "content": row["content"][:300],
                        "issues": issues,
                        "created_at": row["created_at"]
                    })
        
        return violations
    
    def _scan_personas(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        """Scan persona content for Korean validation issues"""
        violations = []
        
        cursor = conn.execute("""
            SELECT id, name, persona_markdown, created_at 
            FROM people 
            ORDER BY created_at DESC
        """)
        
        for row in cursor:
            if row["persona_markdown"]:
                is_valid, issues = self.validator.validate_korean_content(row["persona_markdown"])
                if not is_valid:
                    violations.append({
                        "type": "persona_markdown",
                        "id": row["id"],
                        "name": row["name"],
                        "content": row["persona_markdown"][:300],
                        "issues": issues,
                        "created_at": row["created_at"]
                    })
        
        return violations
    
    def scan_simulation_output_files(self, output_dir: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scan simulation output files for Korean validation issues.
        
        Args:
            output_dir: Directory containing simulation output files
            
        Returns:
            Dictionary of violations by file type
        """
        violations = {
            "json_files": [],
            "markdown_files": [],
            "csv_files": []
        }
        
        if not os.path.exists(output_dir):
            print(f"Output directory not found: {output_dir}")
            return violations
        
        output_path = Path(output_dir)
        
        # Scan JSON files
        for json_file in output_path.rglob("*.json"):
            violations["json_files"].extend(self._scan_json_file(json_file))
        
        # Scan Markdown files
        for md_file in output_path.rglob("*.md"):
            violations["markdown_files"].extend(self._scan_markdown_file(md_file))
        
        # Scan CSV files (if they contain Korean content)
        for csv_file in output_path.rglob("*.csv"):
            violations["csv_files"].extend(self._scan_csv_file(csv_file))
        
        return violations
    
    def _scan_json_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Scan JSON file for Korean validation issues"""
        violations = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Recursively scan JSON content
            self._scan_json_content(data, file_path, violations)
            
        except (json.JSONDecodeError, UnicodeDecodeError, IOError) as e:
            violations.append({
                "type": "file_error",
                "file": str(file_path),
                "content": f"Error reading file: {e}",
                "issues": ["File read error"],
                "created_at": None
            })
        
        return violations
    
    def _scan_json_content(self, data: Any, file_path: Path, violations: List[Dict[str, Any]], path: str = ""):
        """Recursively scan JSON content for Korean validation issues"""
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                self._scan_json_content(value, file_path, violations, current_path)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                current_path = f"{path}[{i}]" if path else f"[{i}]"
                self._scan_json_content(item, file_path, violations, current_path)
        elif isinstance(data, str) and data.strip():
            # Check if string contains Korean characters (likely Korean content)
            if any('\uAC00' <= char <= '\uD7AF' for char in data):
                is_valid, issues = self.validator.validate_korean_content(data)
                if not is_valid:
                    violations.append({
                        "type": "json_content",
                        "file": str(file_path),
                        "path": path,
                        "content": data[:200],
                        "issues": issues,
                        "created_at": None
                    })
    
    def _scan_markdown_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Scan Markdown file for Korean validation issues"""
        violations = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if content contains Korean characters
            if any('\uAC00' <= char <= '\uD7AF' for char in content):
                is_valid, issues = self.validator.validate_korean_content(content)
                if not is_valid:
                    violations.append({
                        "type": "markdown_content",
                        "file": str(file_path),
                        "content": content[:300],
                        "issues": issues,
                        "created_at": None
                    })
            
        except (UnicodeDecodeError, IOError) as e:
            violations.append({
                "type": "file_error",
                "file": str(file_path),
                "content": f"Error reading file: {e}",
                "issues": ["File read error"],
                "created_at": None
            })
        
        return violations
    
    def _scan_csv_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """Scan CSV file for Korean validation issues"""
        violations = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if content contains Korean characters
            if any('\uAC00' <= char <= '\uD7AF' for char in content):
                # Split by lines and check each line
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if line.strip() and any('\uAC00' <= char <= '\uD7AF' for char in line):
                        is_valid, issues = self.validator.validate_korean_content(line)
                        if not is_valid:
                            violations.append({
                                "type": "csv_content",
                                "file": str(file_path),
                                "line": i + 1,
                                "content": line[:200],
                                "issues": issues,
                                "created_at": None
                            })
            
        except (UnicodeDecodeError, IOError) as e:
            violations.append({
                "type": "file_error",
                "file": str(file_path),
                "content": f"Error reading file: {e}",
                "issues": ["File read error"],
                "created_at": None
            })
        
        return violations
    
    def generate_report(self, violations: Dict[str, List[Dict[str, Any]]], output_file: str = None) -> str:
        """
        Generate a comprehensive validation report.
        
        Args:
            violations: Dictionary of violations by content type
            output_file: Optional file to write report to
            
        Returns:
            Report content as string
        """
        report_lines = []
        report_lines.append("# Korean Content Validation Report")
        report_lines.append(f"Generated at: {self._get_timestamp()}")
        report_lines.append("")
        
        total_violations = sum(len(v) for v in violations.values())
        report_lines.append(f"## Summary")
        report_lines.append(f"Total violations found: {total_violations}")
        report_lines.append("")
        
        for content_type, type_violations in violations.items():
            if type_violations:
                report_lines.append(f"### {content_type.replace('_', ' ').title()}")
                report_lines.append(f"Violations: {len(type_violations)}")
                report_lines.append("")
                
                for i, violation in enumerate(type_violations[:10]):  # Show first 10
                    report_lines.append(f"#### Violation {i + 1}")
                    report_lines.append(f"- **Type**: {violation['type']}")
                    if 'id' in violation:
                        report_lines.append(f"- **ID**: {violation['id']}")
                    if 'file' in violation:
                        report_lines.append(f"- **File**: {violation['file']}")
                    if 'sender' in violation:
                        report_lines.append(f"- **Sender**: {violation['sender']}")
                    report_lines.append(f"- **Content**: {violation['content']}")
                    report_lines.append(f"- **Issues**: {', '.join(violation['issues'])}")
                    report_lines.append("")
                
                if len(type_violations) > 10:
                    report_lines.append(f"... and {len(type_violations) - 10} more violations")
                    report_lines.append("")
        
        # Add recommendations
        report_lines.append("## Recommendations")
        if total_violations == 0:
            report_lines.append("✅ No Korean content validation issues found!")
        else:
            report_lines.append("1. Review and fix English text in Korean content")
            report_lines.append("2. Ensure proper Korean sentence structure")
            report_lines.append("3. Use Korean translations for technical terms")
            report_lines.append("4. Check localization string usage in code")
        
        report_content = "\n".join(report_lines)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_content)
            print(f"Report written to: {output_file}")
        
        return report_content
    
    def _get_timestamp(self) -> str:
        """Get current timestamp for report"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    """Main function for command-line usage"""
    parser = argparse.ArgumentParser(description="Validate Korean content in VDOS simulation outputs")
    parser.add_argument("--db-path", help="Path to VDOS database file")
    parser.add_argument("--output-dir", help="Path to simulation output directory")
    parser.add_argument("--report-file", help="Output file for validation report")
    parser.add_argument("--strict", action="store_true", help="Use strict validation mode")
    parser.add_argument("--quiet", action="store_true", help="Suppress console output")
    
    args = parser.parse_args()
    
    scanner = KoreanContentScanner(db_path=args.db_path, strict_mode=args.strict)
    
    all_violations = {}
    
    # Scan database content
    if not args.quiet:
        print("Scanning database content...")
    db_violations = scanner.scan_database_content()
    all_violations.update(db_violations)
    
    # Scan output files if directory provided
    if args.output_dir:
        if not args.quiet:
            print(f"Scanning output files in {args.output_dir}...")
        file_violations = scanner.scan_simulation_output_files(args.output_dir)
        all_violations.update(file_violations)
    
    # Generate report
    report_file = args.report_file or "korean_validation_report.md"
    report_content = scanner.generate_report(all_violations, report_file)
    
    if not args.quiet:
        print("\n" + "="*50)
        print(report_content)
    
    # Exit with error code if violations found
    total_violations = sum(len(v) for v in all_violations.values())
    sys.exit(1 if total_violations > 0 else 0)


if __name__ == "__main__":
    main()