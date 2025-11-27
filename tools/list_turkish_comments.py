
import json
from collections import defaultdict

def main():
    try:
        with open('reports/code_standards_compliance.json', 'r') as f:
            data = json.load(f)
        
        violations = data.get('violations', [])
        turkish_violations = [
            v for v in violations 
            if v['rule'] in ('NON_ENGLISH_COMMENT', 'NON_ENGLISH_DOCSTRING')
        ]
        
        files = defaultdict(int)
        for v in turkish_violations:
            files[v['file']] += 1
            
        print(f"Total Turkish violations: {len(turkish_violations)}")
        print(f"Files affected: {len(files)}")
        print("\nFiles by violation count:")
        
        for file, count in sorted(files.items(), key=lambda x: x[1], reverse=True):
            print(f"{count:3d} - {file}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
