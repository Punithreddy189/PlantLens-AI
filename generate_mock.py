import torch
from CNN import CNN

# Initialize the model with 39 classes (as expected by app.py)
model = CNN(39)

# Save the initialized random weights to the required filename
torch.save(model.state_dict(), 'plant_disease_model_1_latest.pt')

print("Mock model generated successfully: plant_disease_model_1_latest.pt")
