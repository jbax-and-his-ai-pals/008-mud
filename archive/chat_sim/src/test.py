import torch

cuda_available = torch.cuda.is_available()
print(f"Is CUDA available? {cuda_available}")

if cuda_available:
    print(f"Current device: {torch.cuda.get_device_name(0)}")
    device = "cuda"
else:
    print("CUDA not found. Falling back to CPU.")
    device = "cpu"

print(f"DEVICE == '{device.upper()}'")