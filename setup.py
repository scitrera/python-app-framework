import setuptools

with open("README.md", 'r') as f:
    readme_txt = f.read()

setuptools.setup(
    name="scitrera-app-framework",
    version="0.0.66",
    author="Scitrera LLC",
    author_email="open-source-team@scitrera.com",
    description="Common Application Framework Code and Utilities",
    long_description=readme_txt,
    long_description_content_type="text/markdown",
    url="https://github.com/scitrera/python-app-framework",
    packages=setuptools.find_packages(),
    install_requires=[
        'botwinick-utils>=0.0.20',
        'vpd',
        'python-json-logger>=4.0.0',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: BSD License',
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.9',
)
