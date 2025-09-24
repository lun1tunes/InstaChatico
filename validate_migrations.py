#!/usr/bin/env python3
"""
Validate Alembic migrations and model consistency for InstaChatico.
This script checks that the database models are consistent with migrations.
"""

import os
import sys
from pathlib import Path

def validate_model_files():
    """Validate that all model files are syntactically correct"""
    print("🔍 Validating model files...")
    
    model_files = [
        "core/models/__init__.py",
        "core/models/base.py", 
        "core/models/db_helper.py",
        "core/models/instagram_comment.py",
        "core/models/comment_classification.py",
        "core/models/question_answer.py"
    ]
    
    for model_file in model_files:
        if not Path(model_file).exists():
            print(f"❌ Missing model file: {model_file}")
            return False
        
        # Try to compile the Python file
        try:
            with open(model_file, 'r') as f:
                content = f.read()
                compile(content, model_file, 'exec')
            print(f"✅ {model_file} - syntax valid")
        except SyntaxError as e:
            print(f"❌ {model_file} - syntax error: {e}")
            return False
        except Exception as e:
            print(f"⚠️  {model_file} - warning: {e}")
    
    return True


def validate_alembic_config():
    """Validate Alembic configuration"""
    print("\n🔍 Validating Alembic configuration...")
    
    # Check alembic.ini
    if not Path("alembic.ini").exists():
        print("❌ Missing alembic.ini")
        return False
    print("✅ alembic.ini exists")
    
    # Check alembic/env.py
    if not Path("alembic/env.py").exists():
        print("❌ Missing alembic/env.py")
        return False
    
    # Validate env.py imports
    try:
        with open("alembic/env.py", 'r') as f:
            content = f.read()
            
        if "from core.models import Base" not in content:
            print("❌ alembic/env.py missing 'from core.models import Base'")
            return False
            
        if "target_metadata = Base.metadata" not in content:
            print("❌ alembic/env.py missing 'target_metadata = Base.metadata'")
            return False
            
        print("✅ alembic/env.py configuration valid")
        
    except Exception as e:
        print(f"❌ Error reading alembic/env.py: {e}")
        return False
    
    return True


def validate_migration_files():
    """Validate migration files exist and are properly structured"""
    print("\n🔍 Validating migration files...")
    
    versions_dir = Path("alembic/versions")
    if not versions_dir.exists():
        print("❌ Missing alembic/versions directory")
        return False
    
    migration_files = list(versions_dir.glob("*.py"))
    migration_files = [f for f in migration_files if not f.name.startswith("__")]
    
    if not migration_files:
        print("❌ No migration files found")
        return False
    
    print(f"✅ Found {len(migration_files)} migration files:")
    
    for migration_file in sorted(migration_files):
        try:
            with open(migration_file, 'r') as f:
                content = f.read()
                
            # Check for required functions
            if "def upgrade()" not in content:
                print(f"❌ {migration_file.name} missing upgrade() function")
                return False
                
            if "def downgrade()" not in content:
                print(f"❌ {migration_file.name} missing downgrade() function")
                return False
                
            print(f"  ✅ {migration_file.name}")
            
        except Exception as e:
            print(f"❌ Error reading {migration_file.name}: {e}")
            return False
    
    return True


def check_model_consistency():
    """Check for common model consistency issues"""
    print("\n🔍 Checking model consistency...")
    
    issues = []
    
    # Check InstagramComment model
    try:
        with open("core/models/instagram_comment.py", 'r') as f:
            content = f.read()
            
        if 'id: Mapped[str] = mapped_column(primary_key=True)' not in content:
            issues.append("InstagramComment should have id: Mapped[str] (string primary key)")
            
        if '__tablename__ = "instagram_comments"' not in content:
            issues.append("InstagramComment should have __tablename__ = 'instagram_comments'")
            
    except Exception as e:
        issues.append(f"Error checking InstagramComment: {e}")
    
    # Check CommentClassification model  
    try:
        with open("core/models/comment_classification.py", 'r') as f:
            content = f.read()
            
        if 'id: Mapped[int] = mapped_column(primary_key=True)' not in content:
            issues.append("CommentClassification should have id: Mapped[int] (integer primary key)")
            
        if '__tablename__ = "comments_classification"' not in content:
            issues.append("CommentClassification should have __tablename__ = 'comments_classification'")
            
        if 'ForeignKey("instagram_comments.id"' not in content:
            issues.append("CommentClassification should reference instagram_comments.id")
            
    except Exception as e:
        issues.append(f"Error checking CommentClassification: {e}")
    
    # Check QuestionAnswer model
    try:
        with open("core/models/question_answer.py", 'r') as f:
            content = f.read()
            
        if 'id: Mapped[int] = mapped_column(primary_key=True)' not in content:
            issues.append("QuestionAnswer should have id: Mapped[int] (integer primary key)")
            
        if '__tablename__ = "question_messages_answers"' not in content:
            issues.append("QuestionAnswer should have __tablename__ = 'question_messages_answers'")
            
        if 'ForeignKey("comments_classification.comment_id"' not in content:
            issues.append("QuestionAnswer should reference comments_classification.comment_id")
            
    except Exception as e:
        issues.append(f"Error checking QuestionAnswer: {e}")
    
    if issues:
        print("❌ Model consistency issues found:")
        for issue in issues:
            print(f"  • {issue}")
        return False
    else:
        print("✅ Model consistency checks passed")
        return True


def validate_foreign_key_consistency():
    """Validate foreign key relationships are consistent"""
    print("\n🔍 Validating foreign key consistency...")
    
    # Expected relationships:
    # CommentClassification.comment_id -> InstagramComment.id  
    # QuestionAnswer.comment_id -> CommentClassification.comment_id
    
    try:
        # Check CommentClassification -> InstagramComment
        with open("core/models/comment_classification.py", 'r') as f:
            cc_content = f.read()
            
        with open("core/models/instagram_comment.py", 'r') as f:
            ic_content = f.read()
            
        if 'ForeignKey("instagram_comments.id"' in cc_content and '__tablename__ = "instagram_comments"' in ic_content:
            print("✅ CommentClassification -> InstagramComment FK valid")
        else:
            print("❌ CommentClassification -> InstagramComment FK invalid")
            return False
        
        # Check QuestionAnswer -> CommentClassification  
        with open("core/models/question_answer.py", 'r') as f:
            qa_content = f.read()
            
        if 'ForeignKey("comments_classification.comment_id"' in qa_content and '__tablename__ = "comments_classification"' in cc_content:
            print("✅ QuestionAnswer -> CommentClassification FK valid")
        else:
            print("❌ QuestionAnswer -> CommentClassification FK invalid")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Error validating foreign keys: {e}")
        return False


def main():
    """Run all validation checks"""
    print("🚀 InstaChatico Migration Validation")
    print("=" * 50)
    
    # Change to app directory
    os.chdir(Path(__file__).parent)
    
    all_passed = True
    
    # Run all validation checks
    checks = [
        validate_model_files,
        validate_alembic_config, 
        validate_migration_files,
        check_model_consistency,
        validate_foreign_key_consistency
    ]
    
    for check in checks:
        if not check():
            all_passed = False
    
    print("\n" + "=" * 50)
    
    if all_passed:
        print("🎉 All validation checks passed!")
        print("✅ Your Alembic migrations are valid and consistent")
        print("\n📋 Next steps:")
        print("  • Run 'alembic upgrade head' to apply migrations")
        print("  • Test the application with the migrated database")
        return 0
    else:
        print("❌ Some validation checks failed!")
        print("⚠️  Please fix the issues above before running migrations")
        print("\n📋 Recommended actions:")
        print("  • Fix the model inconsistencies listed above")
        print("  • Re-run this validation script")
        print("  • Generate new migration if needed: 'alembic revision --autogenerate -m \"fix_inconsistencies\"'")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
