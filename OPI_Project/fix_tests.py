import os

def fix_tests():
    for root, dirs, files in os.walk('tests'):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                new_content = content.replace('opi_abfb', 'opi_s')
                new_content = new_content.replace('opi_ap', 'opi_abp')
                new_content = new_content.replace('achieve_abfb', 'achieve_s')
                new_content = new_content.replace('achieve_ap', 'achieve_abp')
                new_content = new_content.replace('SSS+ABFB', 'S')
                new_content = new_content.replace('"AP"', '"AB+"')
                new_content = new_content.replace("'AP'", "'AB+'")
                new_content = new_content.replace('"abfb"', '"s"')
                new_content = new_content.replace("'abfb'", "'s'")
                new_content = new_content.replace('"ap"', '"abp"')
                new_content = new_content.replace("'ap'", "'abp'")
                
                if new_content != content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)

if __name__ == '__main__':
    fix_tests()
