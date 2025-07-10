import matplotlib.pyplot as plt
import numpy as np

# Example group sizes (change as you like)
group_sizes = np.array([1, 5, 10, 50, 100])

slopes = np.linspace(-100, 100, 201)
proportions = []

for slope in slopes:
    if slope >= 0:
        exp = 1 - (slope / 100)
        exp = max(0.01, exp)
        powered = group_sizes ** exp
    else:
        exp = 1 + (slope / 100)
        exp = max(0.01, exp)
        powered = (1 / group_sizes) ** exp
    p = powered / powered.sum()
    proportions.append(p)

proportions = np.array(proportions)

plt.figure(figsize=(10, 6))
for i, size in enumerate(group_sizes):
    plt.plot(slopes, proportions[:, i], label=f'Group size {size}')

plt.xlabel('Slope')
plt.ylabel('Proportion')
plt.title('Effect of Slope on Group Proportions')
plt.legend()
plt.grid(True)
plt.show()