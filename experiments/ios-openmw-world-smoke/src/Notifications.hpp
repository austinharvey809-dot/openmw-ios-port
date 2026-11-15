#pragma once
#include "Resources.hpp"
#include <osg/Notify>
#include <atomic>
#include <functional>
#include <mutex>

namespace G4 {
// Callback invocation and closure are serialized. No renderer/controller capture
// is retained after close(), including callbacks concurrent with shutdown.
class NotificationSink : public osg::NotifyHandler {
    std::mutex mutex;
    std::function<void(const std::string&)> callback;
    std::atomic<unsigned> warningCount{0},callbackErrors{0};
public:
    explicit NotificationSink(std::function<void(const std::string&)> value):callback(std::move(value)){}
    unsigned warnings()const{return warningCount.load();}
    unsigned errors()const{return callbackErrors.load();}
    void write(const std::string& message)noexcept{
        std::lock_guard lock(mutex);
        if(callback)try{callback(message);}catch(...){++callbackErrors;}
    }
    void notify(osg::NotifySeverity level,const char* message)override{
        if(level<=osg::WARN)++warningCount;
        write("OSG["+std::to_string(level)+"] "+(message?message:"<null>"));
    }
    void close(){std::lock_guard lock(mutex);callback={};}
};

class NotificationScope {
    osg::ref_ptr<osg::NotifyHandler> previous;
    osg::ref_ptr<NotificationSink> sink;
    osg::NotifySeverity level;
public:
    explicit NotificationScope(std::function<void(const std::string&)> callback){
        std::lock_guard registry(CapabilityRegistryMutex);
        previous=osg::getNotifyHandler();level=osg::getNotifyLevel();
        sink=new NotificationSink(std::move(callback));
        osg::setNotifyHandler(sink);osg::setNotifyLevel(osg::WARN);
    }
    NotificationSink* get()const{return sink;}
    ~NotificationScope(){
        std::lock_guard registry(CapabilityRegistryMutex);
        sink->close();
        if(osg::getNotifyHandler()==sink.get()){osg::setNotifyHandler(previous);osg::setNotifyLevel(level);}
    }
};
}
