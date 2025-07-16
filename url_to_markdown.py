#!/usr/bin/env python
import os
import sys
import subprocess

def install_dependencies():
    try:
        import uv
    except ImportError:
        print("uv not found. Installing uv...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "uv"])

    subprocess.check_call([sys.executable, "-m", "uv", "pip", "install", "requests", "html2text"])

if __name__ == "__main__":
    install_dependencies()
    import requests
    import html2text
    import argparse

    def convert_url_to_markdown(url):
        """
        Converts the content of a given URL to Markdown using Jina AI's Reader API.

        Args:
            url (str): The URL of the webpage to convert.

        Returns:
            str: The Markdown content of the webpage.
        """
        try:
            # Use Jina AI's Reader API to fetch the content of the URL
            reader_url = f"https://r.jina.ai/{url}"
            response = requests.get(reader_url)
            response.raise_for_status()  # Raise an exception for bad status codes

            # Convert the HTML content to Markdown
            html_content = response.text
            markdown_converter = html2text.HTML2Text()
            markdown_converter.body_width = 0
            markdown_content = markdown_converter.handle(html_content)

            return markdown_content

        except requests.exceptions.RequestException as e:
            return f"Error fetching URL: {e}"

    parser = argparse.ArgumentParser(description="Convert a webpage to Markdown using Jina AI.")
    parser.add_argument("url", help="The URL of the webpage to convert.")
    args = parser.parse_args()

    markdown_output = convert_url_to_markdown(args.url)
    print(markdown_output)
