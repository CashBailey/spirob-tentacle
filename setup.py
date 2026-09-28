"""Setup file for spirob ROS2 package."""

import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'spirob'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        # Package index marker
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        # Package manifest
        ('share/' + package_name, ['package.xml']),
        # Config files
        (os.path.join('share', package_name, 'config'),
            glob(os.path.join('config', '*.yaml'))),
        # Launch files
        (os.path.join('share', package_name, 'launch'),
            glob(os.path.join('launch', '*.launch.py'))),
    ],
    install_requires=[
        'setuptools',
        'pyserial',
        'PyQt6',
        'pyqtgraph',
        'pygame',
        'pyyaml',
    ],
    zip_safe=True,
    maintainer='Cash',
    maintainer_email='c@todo.todo',
    description='SpiRob 3-tendon soft robot servo driver for ROS2',
    license='Proprietary',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'spirob_bus = spirob.main:main',
            'spirob_gui = spirob.gui.main:main',
        ],
    },
)
