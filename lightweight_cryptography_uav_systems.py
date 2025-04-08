import subprocess
import time
import os
import psutil
import tracemalloc
import matplotlib.pyplot as plt
import datetime
import csv
from ina219 import INA219, DeviceRangeError
from threading import Thread

TEST_MESSAGE = "in a case of superiority".encode()
ALGORITHMS = {
    "Ascon": "/home/raspberry-pi/diploma/algorithms/ascon",
    "Elephant": "/home/raspberry-pi/diploma/algorithms/elephant",
    "GIFT-COFB": "/home/raspberry-pi/diploma/algorithms/gift-cofb",
    "Xoodyak": "/home/raspberry-pi/diploma/algorithms/xoodyak"
}
SHUNT_OHMS = 0.1
MAX_EXPECTED_AMPS = 2.0
ina = INA219(SHUNT_OHMS, MAX_EXPECTED_AMPS, address=0x40, busnum=1)
ina.configure(ina.RANGE_16V)

def read_ina219():
    try:
        return ina.voltage(), -ina.current(), ina.power()
    except DeviceRangeError:
        return 0, 0, 0

def run_command(command, cwd=None):
    process = subprocess.Popen(command, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process

def benchmark_algorithm(name, path, results):
    print(f"\nTesting {name}...\n")

    tracemalloc.start()
    cpu_usage, ram_usage, timestamps = [], [], []
    voltage_list, current_list, power_list = [], [], []
    start_time = time.time()

    process = subprocess.Popen(["make", "benchmark"], cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    while process.poll() is None:
        cpu_usage.append(psutil.cpu_percent())
        ram_usage.append(psutil.virtual_memory().used / (1024 * 1024))
        voltage, current, power = read_ina219()
        voltage_list.append(voltage)
        current_list.append(current)
        power_list.append(power)
        timestamps.append(time.time() - start_time)
        time.sleep(0.5)

    tracemalloc.stop()
    results[name] = {
        "timestamps": timestamps,
        "cpu_usage": cpu_usage,
        "ram_usage": ram_usage,
        "voltage": voltage_list,
        "current": current_list,
        "power": power_list
    }

def save_plot(x, y, xlabel, ylabel, title, filename):
    plt.figure()
    plt.plot(x, y, label=title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.savefig(filename)
    plt.close()

def save_comparison_plots(results, metric, ylabel, title, filename):
    plt.figure()
    for algo, data in results.items():
        plt.plot(data["timestamps"], data[metric], label=algo)
    plt.xlabel("Time (s)")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.savefig(filename)
    plt.close()

def save_results_to_csv(results, filename):
    with open(filename, mode='w', newline='') as csvfile:
        fieldnames = ['Algorithm', 'Timestamp', 'CPU Usage (%)', 'RAM Usage (MB)', 'Voltage (V)', 'Current (mA)', 'Power (mW)']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for algo, data in results.items():
            for i in range(len(data['timestamps'])):
                writer.writerow({
                    'Algorithm': algo,
                    'Timestamp': data['timestamps'][i],
                    'CPU Usage (%)': data['cpu_usage'][i],
                    'RAM Usage (MB)': data['ram_usage'][i],
                    'Voltage (V)': data['voltage'][i],
                    'Current (mA)': data['current'][i],
                    'Power (mW)': data['power'][i]
                })

def main():
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    result_dir = f"benchmark_results_{timestamp}_key_128bit"
    os.makedirs(result_dir, exist_ok=True)
    results = {}

    print("\nStart ArduPilot SITL...\n")
    sitl_process = run_command("sim_vehicle.py -v ArduCopter -w")
    time.sleep(10)

    print("\nStart MAVProxy...\n")
    mavproxy_process = run_command("mavproxy.py --master tcp:127.0.0.1:5760 --console --map")
    time.sleep(5)

    for algo, path in ALGORITHMS.items():
        benchmark_algorithm(algo, path, results)

    sitl_process.terminate()
    mavproxy_process.terminate()

    for algo, data in results.items():
        save_plot(data["timestamps"], data["cpu_usage"], "Time (s)", "CPU Usage (%)", f"CPU Usage - {algo}", f"{result_dir}/cpu_usage_{algo.lower()}.png")
        save_plot(data["timestamps"], data["ram_usage"], "Time (s)", "RAM Usage (MB)", f"RAM Usage - {algo}", f"{result_dir}/ram_usage_{algo.lower()}.png")
        save_plot(data["timestamps"], data["power"], "Time (s)", "Power (mW)", f"Power Usage - {algo}", f"{result_dir}/power_usage_{algo.lower()}.png")
        save_plot(data["timestamps"], data["voltage"], "Time (s)", "Voltage (V)", f"Voltage - {algo}", f"{result_dir}/voltage_{algo.lower()}.png")
        save_plot(data["timestamps"], data["current"], "Time (s)", "Current (mA)", f"Current - {algo}", f"{result_dir}/current_{algo.lower()}.png")

    # Save comparison plots
    save_comparison_plots(results, "cpu_usage", "CPU Usage (%)", "CPU Usage Comparison", f"{result_dir}/cpu_usage_comparison.png")
    save_comparison_plots(results, "ram_usage", "RAM Usage (MB)", "RAM Usage Comparison", f"{result_dir}/ram_usage_comparison.png")
    save_comparison_plots(results, "power", "Power (mW)", "Power Usage Comparison", f"{result_dir}/power_usage_comparison.png")
    save_comparison_plots(results, "voltage", "Voltage (V)", "Voltage Comparison", f"{result_dir}/voltage_comparison.png")
    save_comparison_plots(results, "current", "Current (mA)", "Current Comparison", f"{result_dir}/current_comparison.png")

    # Save results to CSV
    csv_filename = f"{result_dir}/benchmark_results.csv"
    save_results_to_csv(results, csv_filename)
    print(f"Results saved to {csv_filename}")

if __name__ == "__main__":
    main()
