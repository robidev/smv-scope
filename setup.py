from setuptools import find_packages, setup

setup(
    name='smvScope',
    author='Robin',
    author_email='robin.dev@gmail.com',
    url='https://github.com/robidev',
    version='1.0.0',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    scripts = ["smvscope"],
    install_requires=[
        'flask>=1.0.2',
    ],
)


