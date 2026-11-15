#pragma once
#include "Resources.hpp"
#include <functional>
#include <map>
#include <set>
#include <stdexcept>

namespace G4 {
struct InputProfile {
    std::vector<std::string> content{"Morrowind.esm"},archives{"Morrowind.bsa"},looseDirectories;
    std::map<std::string,std::string> files;
    static std::filesystem::path resolve(const std::filesystem::path& root,const std::string& name){
        const std::filesystem::path relative(name);
        if(name.empty()||name.find('\\')!=std::string::npos||name.find(':')!=std::string::npos||relative.has_root_path())
            throw std::runtime_error("G4 unsafe private profile path");
        auto current=root;
        for(const auto& component:relative){
            if(component.empty()||component=="."||component=="..")throw std::runtime_error("G4 unsafe private profile component");
            current/=component;
            if(std::filesystem::is_symlink(std::filesystem::symlink_status(current)))throw std::runtime_error("G4 linked private input");
        }
        const auto base=std::filesystem::canonical(root),path=std::filesystem::canonical(current);
        const auto within=path.lexically_relative(base);
        if(within.empty()||*within.begin()=="..")throw std::runtime_error("G4 private input escaped import directory");
        return path;
    }
    void verify(const std::filesystem::path& root,const std::function<std::string(const std::filesystem::path&)>& hash)const{
        if(content.empty()||content.size()>254||archives.empty()||archives.size()>32||looseDirectories.size()>8)
            throw std::runtime_error("G4 private profile input budget exceeded");
        if(std::filesystem::is_symlink(std::filesystem::symlink_status(root)))throw std::runtime_error("G4 linked import directory");
        std::set<std::string> inventory;
        auto file=[&](const std::string& name){
            const auto path=resolve(root,name);
            if(!std::filesystem::is_regular_file(path)||!inventory.insert(name).second)
                throw std::runtime_error("G4 missing/nonregular/duplicate private input");
        };
        for(const auto& name:content)file(name);
        for(const auto& name:archives)file(name);
        for(const auto& name:looseDirectories){
            const auto directory=resolve(root,name);
            if(!std::filesystem::is_directory(directory))throw std::runtime_error("G4 loose input is not a directory");
            for(const auto& entry:std::filesystem::recursive_directory_iterator(directory)){
                const auto relative=entry.path().lexically_relative(root).generic_string();
                resolve(root,relative);
                if(entry.is_regular_file())file(relative);
                else if(!entry.is_directory())throw std::runtime_error("G4 unsupported private filesystem entry");
            }
        }
        if(inventory.size()!=files.size())throw std::runtime_error("G4 exact private file inventory mismatch");
        for(const auto& name:inventory){
            const auto found=files.find(name);
            if(found==files.end()||found->second.size()!=64||found->second.find_first_not_of("0123456789abcdef")!=std::string::npos)
                throw std::runtime_error("G4 missing/invalid private SHA-256");
            if(hash(resolve(root,name))!=found->second)throw std::runtime_error("G4 private SHA-256 mismatch: "+name);
        }
    }
    std::vector<std::filesystem::path> contentPaths(const std::filesystem::path& root)const{
        std::vector<std::filesystem::path> result;for(const auto& name:content)result.push_back(resolve(root,name));return result;
    }
    ResourcePaths resourcePaths(const std::filesystem::path& root)const{
        ResourcePaths result;for(const auto& name:archives)result.archives.push_back(resolve(root,name));
        for(const auto& name:looseDirectories)result.looseDirectories.push_back(resolve(root,name));return result;
    }
};
}
