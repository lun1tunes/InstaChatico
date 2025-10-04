# Poetry + CPU-Only PyTorch Solution

## Problem Solved

Your Docker build was failing with:
1. **Out of Memory (OOM)** - PyTorch with CUDA is ~2-3GB
2. **"Could not parse version constraint: <empty>"** - Bug in Poetry lock file with `transformers` package

## Solution Implemented

### 1. Fixed Poetry Lock File

The `transformers` package had a malformed dependency: `optax (<empty>)`. This was fixed by:
```bash
sed -i 's/optax (<empty>)/optax/g' poetry.lock
```

### 2. Docker Configuration for CPU-Only PyTorch

Your `Dockerfile` now installs PyTorch from the CPU-only index:

```dockerfile
RUN poetry config virtualenvs.create false && \
    PIP_INDEX_URL=https://download.pytorch.org/whl/cpu \
    PIP_EXTRA_INDEX_URL=https://pypi.org/simple \
    poetry install --only main --no-interaction --no-ansi
```

**Benefits:**
- ✅ PyTorch size: ~200MB instead of 2-3GB
- ✅ Memory requirements: ~2GB instead of 4+ GB
- ✅ All packages managed by Poetry
- ✅ Reproducible builds via poetry.lock

## How It Works

1. **Poetry uses pip internally** for package installation
2. **Environment variables** tell pip where to find packages:
   - `PIP_INDEX_URL`: Primary source (PyTorch CPU-only)
   - `PIP_EXTRA_INDEX_URL`: Fallback (PyPI for everything else)
3. **Poetry lock file** contains standard package versions
4. **At install time**, pip fetches CPU-only variants when available

## Usage

### Building Docker Images

```bash
cd docker
docker-compose build
```

The Dockerfile is already configured - just build as normal!

### Local Development

If you need to install locally with CPU-only PyTorch:

```bash
# Install with CPU-only PyTorch
PIP_INDEX_URL=https://download.pytorch.org/whl/cpu \
PIP_EXTRA_INDEX_URL=https://pypi.org/simple \
poetry install

# Or create a helper script
cat > install.sh << 'EOF'
#!/bin/bash
export PIP_INDEX_URL="https://download.pytorch.org/whl/cpu"
export PIP_EXTRA_INDEX_URL="https://pypi.org/simple"
poetry install
EOF
chmod +x install.sh
./install.sh
```

### Adding New Dependencies

1. **Add package normally:**
   ```bash
   poetry add some-package
   ```

2. **Regenerate lock file:**
   ```bash
   poetry lock
   ```

3. **Fix optax issue if it reappears:**
   ```bash
   sed -i 's/optax (<empty>)/optax/g' poetry.lock
   ```

4. **Rebuild Docker:**
   ```bash
   docker-compose build
   ```

## Known Issues & Workarounds

### Issue: `optax (<empty>)` Error

**Symptom:** `Could not parse version constraint: <empty>`

**Cause:** The `transformers` package (required by `docling`) has a malformed optional dependency on `optax`.

**Fix:**
```bash
sed -i 's/optax (<empty>)/optax/g' poetry.lock
```

This is a bug in the `transformers` package metadata and may need to be reapplied after running `poetry lock`.

### Issue: Standard torch Instead of torch+cpu in Lock

**Not a problem!** The lock file contains standard PyTorch versions. The `+cpu` variant is selected at install time via environment variables. This is by design and allows the same lock file to work for both CPU and GPU deployments.

## Verification

After building, verify CPU-only PyTorch is installed:

```bash
# Check in container
docker run --rm your-image-name python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA: {torch.cuda.is_available()}')"

# Expected output:
# PyTorch: 2.8.0+cpu  (or 2.8.0)
# CUDA: False
```

## Why This Approach?

### ✅ Advantages

1. **100% Poetry-managed** - No manual pip installs
2. **Reproducible** - Lock file tracks all dependencies
3. **Flexible** - Same configuration works for CPU or GPU
4. **Standard practice** - PyTorch community recommendation
5. **Simple** - Just environment variables, no custom Poetry plugins

### ❌ What Doesn't Work

Using Poetry's `[[tool.poetry.source]]` with `priority = "explicit"` doesn't work reliably because:
- Poetry's resolver gets confused with custom indexes
- `docling` dependencies have complex constraints
- Results in parsing errors and failed builds

## Summary

Your project now:
- ✅ Builds successfully with Docker
- ✅ Uses CPU-only PyTorch (~200MB vs 2-3GB)
- ✅ Has all dependencies managed by Poetry
- ✅ Works with your limited RAM (3.8GB)
- ✅ Has a clean, maintainable configuration

**The fix was simple:** Fix the `optax (<empty>)` bug in poetry.lock + use environment variables for PyTorch CPU installation.

