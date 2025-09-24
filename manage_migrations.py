#!/usr/bin/env python3
"""
Alembic migration management script for InstaChatico.
Provides easy commands for common migration operations.
"""

import os
import sys
import subprocess
from pathlib import Path
import argparse


def run_command(cmd, description):
    """Run a shell command and handle errors"""
    print(f"🔄 {description}")
    print(f"   Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout:
            print(f"   Output: {result.stdout.strip()}")
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed!")
        print(f"   Error: {e.stderr.strip() if e.stderr else str(e)}")
        return False
    except FileNotFoundError:
        print(f"❌ Command not found. Make sure alembic is installed: pip install alembic")
        return False


def check_current_revision():
    """Check the current database revision"""
    print("🔍 Checking current database revision...")
    
    cmd = ["alembic", "current"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        if result.stdout.strip():
            print(f"✅ Current revision: {result.stdout.strip()}")
        else:
            print("⚠️  No current revision (database may be empty)")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to check current revision: {e.stderr.strip() if e.stderr else str(e)}")
        return False


def check_pending_migrations():
    """Check for pending migrations"""
    print("🔍 Checking for pending migrations...")
    
    # Get current revision
    try:
        current_result = subprocess.run(["alembic", "current"], capture_output=True, text=True, check=True)
        current_rev = current_result.stdout.strip()
        
        # Get head revision
        head_result = subprocess.run(["alembic", "heads"], capture_output=True, text=True, check=True)
        head_rev = head_result.stdout.strip()
        
        if current_rev and head_rev:
            if current_rev == head_rev:
                print("✅ Database is up to date")
                return True
            else:
                print(f"⚠️  Database needs upgrade: {current_rev} -> {head_rev}")
                return False
        else:
            print("⚠️  Unable to determine migration status")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to check migration status: {e.stderr.strip() if e.stderr else str(e)}")
        return False


def upgrade_database():
    """Upgrade database to latest revision"""
    return run_command(["alembic", "upgrade", "head"], "Upgrading database to latest revision")


def downgrade_database(revision="base"):
    """Downgrade database to specified revision"""
    return run_command(["alembic", "downgrade", revision], f"Downgrading database to {revision}")


def show_migration_history():
    """Show migration history"""
    return run_command(["alembic", "history", "--verbose"], "Showing migration history")


def generate_migration(message):
    """Generate a new migration"""
    if not message:
        print("❌ Migration message is required")
        return False
    
    return run_command(["alembic", "revision", "--autogenerate", "-m", message], f"Generating migration: {message}")


def show_current_status():
    """Show comprehensive migration status"""
    print("📊 InstaChatico Migration Status")
    print("=" * 50)
    
    # Check if alembic is available
    try:
        subprocess.run(["alembic", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Alembic not found. Install with: pip install alembic")
        return False
    
    # Check database connection
    print("🔍 Checking database connection...")
    try:
        # Try to run a simple alembic command to test DB connection
        subprocess.run(["alembic", "current"], capture_output=True, text=True, check=True)
        print("✅ Database connection successful")
    except subprocess.CalledProcessError as e:
        print(f"❌ Database connection failed: {e.stderr.strip() if e.stderr else str(e)}")
        print("   Check your DATABASE_URL in environment variables")
        return False
    
    # Show current revision
    check_current_revision()
    
    # Check for pending migrations
    check_pending_migrations()
    
    # Count migration files
    versions_dir = Path("alembic/versions")
    if versions_dir.exists():
        migration_files = list(versions_dir.glob("*.py"))
        migration_files = [f for f in migration_files if not f.name.startswith("__")]
        print(f"📁 Total migration files: {len(migration_files)}")
    
    print("=" * 50)
    return True


def validate_before_migration():
    """Run validation before applying migrations"""
    print("🔍 Running pre-migration validation...")
    
    # Run our validation script
    try:
        result = subprocess.run([sys.executable, "validate_migrations.py"], 
                              capture_output=True, text=True, check=True)
        print("✅ Pre-migration validation passed")
        return True
    except subprocess.CalledProcessError as e:
        print("❌ Pre-migration validation failed!")
        if e.stdout:
            print(e.stdout)
        if e.stderr:
            print(e.stderr)
        return False


def safe_upgrade():
    """Safely upgrade database with validation"""
    print("🚀 Safe Database Upgrade")
    print("=" * 30)
    
    # Step 1: Validate
    if not validate_before_migration():
        print("❌ Validation failed. Aborting upgrade.")
        return False
    
    # Step 2: Check status
    if not show_current_status():
        print("❌ Status check failed. Aborting upgrade.")
        return False
    
    # Step 3: Confirm with user (if interactive)
    if sys.stdin.isatty():
        response = input("\n🤔 Proceed with database upgrade? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            print("❌ Upgrade cancelled by user.")
            return False
    
    # Step 4: Upgrade
    if upgrade_database():
        print("\n🎉 Database upgrade completed successfully!")
        return True
    else:
        print("\n❌ Database upgrade failed!")
        return False


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description="InstaChatico Migration Management")
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    subparsers.add_parser('status', help='Show migration status')
    
    # Upgrade command
    subparsers.add_parser('upgrade', help='Upgrade database to latest revision')
    
    # Safe upgrade command
    subparsers.add_parser('safe-upgrade', help='Safely upgrade with validation')
    
    # Downgrade command
    downgrade_parser = subparsers.add_parser('downgrade', help='Downgrade database')
    downgrade_parser.add_argument('revision', nargs='?', default='base', 
                                help='Revision to downgrade to (default: base)')
    
    # History command
    subparsers.add_parser('history', help='Show migration history')
    
    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate new migration')
    generate_parser.add_argument('message', help='Migration message')
    
    # Validate command
    subparsers.add_parser('validate', help='Validate migrations')
    
    args = parser.parse_args()
    
    # Change to app directory
    os.chdir(Path(__file__).parent)
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute commands
    success = True
    
    if args.command == 'status':
        success = show_current_status()
    elif args.command == 'upgrade':
        success = upgrade_database()
    elif args.command == 'safe-upgrade':
        success = safe_upgrade()
    elif args.command == 'downgrade':
        success = downgrade_database(args.revision)
    elif args.command == 'history':
        success = show_migration_history()
    elif args.command == 'generate':
        success = generate_migration(args.message)
    elif args.command == 'validate':
        success = validate_before_migration()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
